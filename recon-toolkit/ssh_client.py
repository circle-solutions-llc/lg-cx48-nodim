"""SSH client wrapper for communicating with rooted LG webOS TV."""

import json

import paramiko


class TVSSHClient:
    """Manages SSH connection to a rooted LG webOS TV."""

    def __init__(self, host: str, port: int = 22, username: str = "root",
                 password: str = "alpine", key_path: str | None = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self._client: paramiko.SSHClient | None = None

    def connect(self):
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
        }
        if self.key_path:
            kwargs["key_filename"] = self.key_path
        else:
            kwargs["password"] = self.password

        self._client.connect(**kwargs)

    def exec(self, command: str, timeout: int = 30) -> str:
        """Execute a command and return stdout."""
        if not self._client:
            raise RuntimeError("Not connected")
        _, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        output = stdout.read().decode("utf-8", errors="replace")
        errors = stderr.read().decode("utf-8", errors="replace")
        if errors and not output:
            return errors
        return output

    def exec_json(self, command: str, timeout: int = 30) -> dict | list | None:
        """Execute a command and parse stdout as JSON."""
        output = self.exec(command, timeout=timeout)
        try:
            return json.loads(output)
        except (json.JSONDecodeError, ValueError):
            return {"raw_output": output}

    def luna_send(self, uri: str, params: dict | None = None, timeout: int = 10) -> dict:
        """Call a luna service and return the JSON response."""
        params_str = json.dumps(params) if params else "{}"
        cmd = f"luna-send -n 1 -f '{uri}' '{params_str}'"
        return self.exec_json(cmd, timeout=timeout)

    def luna_send_pub(self, uri: str, params: dict | None = None, timeout: int = 10) -> dict:
        """Call a luna service via luna-send-pub (public bus)."""
        params_str = json.dumps(params) if params else "{}"
        cmd = f"luna-send-pub -n 1 -f '{uri}' '{params_str}'"
        return self.exec_json(cmd, timeout=timeout)

    def file_exists(self, path: str) -> bool:
        result = self.exec(f"test -e '{path}' && echo 'exists' || echo 'missing'")
        return "exists" in result

    def read_file(self, path: str) -> str:
        return self.exec(f"cat '{path}'")

    def list_dir(self, path: str) -> list[str]:
        output = self.exec(f"ls -la '{path}' 2>/dev/null")
        return [line for line in output.strip().split("\n") if line]

    def find_files(self, path: str, pattern: str, max_depth: int = 5) -> list[str]:
        output = self.exec(
            f"find '{path}' -maxdepth {max_depth} -name '{pattern}' 2>/dev/null"
        )
        return [line.strip() for line in output.strip().split("\n") if line.strip()]

    def get_tv_info(self) -> dict:
        """Gather basic TV information."""
        info = {}

        # OS info
        os_info = self.luna_send(
            "luna://com.webos.service.systemservice/osInfo/query",
            {"parameters": ["webos_manufacturing_version", "webos_release",
                            "webos_build_datetime", "device_name"]}
        )
        if isinstance(os_info, dict):
            info["webos_version"] = os_info.get("webos_release", "unknown")
            info["firmware"] = os_info.get("webos_manufacturing_version", "unknown")
            info["build_date"] = os_info.get("webos_build_datetime", "unknown")
            info["device_name"] = os_info.get("device_name", "unknown")

        # Model name
        model_info = self.luna_send(
            "luna://com.webos.service.config/getConfigs",
            {"configNames": ["tv.model.modelId", "tv.model.serialnumber"]}
        )
        if isinstance(model_info, dict):
            configs = model_info.get("configs", {})
            info["model"] = configs.get("tv.model.modelId", "unknown")

        # Board info from /proc
        info["kernel"] = self.exec("uname -a").strip()
        info["cpu"] = self.exec("cat /proc/cpuinfo | head -20").strip()
        info["memory"] = self.exec("free -m | head -3").strip()

        return info

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
