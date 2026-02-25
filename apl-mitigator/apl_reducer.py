#!/usr/bin/env python3
"""
APL Reducer — Content-side ABL mitigation tool.

Reduces the effective Average Picture Level (APL) of a video signal to keep
it below the ABL trigger threshold, without perceptible visual impact.

Strategies:
1. Zone-based darkening: Slightly darken less-important screen regions
2. Highlight compression: Compress the top 5-10% of brightness range
3. Temporal dithering: Alternate slightly darker/brighter frames
4. Border darkening: Subtly darken screen edges (least visible area)
"""

import argparse
import sys

import numpy as np

try:
    import cv2
except ImportError:
    print("OpenCV required: pip install opencv-python")
    sys.exit(1)


def calculate_apl(frame: np.ndarray) -> float:
    """Calculate Average Picture Level as percentage (0-100)."""
    # Convert to grayscale luminance if color
    if len(frame.shape) == 3:
        # BT.709 luminance weights
        luminance = (
            0.2126 * frame[:, :, 2].astype(float)  # R
            + 0.7152 * frame[:, :, 1].astype(float)  # G
            + 0.0722 * frame[:, :, 0].astype(float)  # B
        )
    else:
        luminance = frame.astype(float)

    return (luminance.mean() / 255.0) * 100.0


def apply_highlight_compression(frame: np.ndarray, threshold_pct: float = 90,
                                 compression: float = 0.7) -> np.ndarray:
    """Compress highlights above a threshold to reduce peak APL.

    Args:
        frame: Input BGR frame
        threshold_pct: Brightness threshold (% of 255) above which to compress
        compression: How much to compress (0=full black, 1=no change)
    """
    threshold = int(255 * threshold_pct / 100)
    result = frame.copy().astype(np.float32)

    # Find pixels above threshold
    mask = result > threshold

    # Compress: new_value = threshold + (value - threshold) * compression
    result[mask] = threshold + (result[mask] - threshold) * compression

    return np.clip(result, 0, 255).astype(np.uint8)


def apply_border_darkening(frame: np.ndarray, border_pct: float = 5,
                           darkening: float = 0.85) -> np.ndarray:
    """Darken screen borders to reduce APL with minimal visual impact.

    Args:
        frame: Input BGR frame
        border_pct: Border width as percentage of screen dimensions
        darkening: Brightness multiplier for border area (0=black, 1=unchanged)
    """
    h, w = frame.shape[:2]
    border_h = int(h * border_pct / 100)
    border_w = int(w * border_pct / 100)

    result = frame.copy().astype(np.float32)

    # Create a vignette-like mask (smooth falloff at borders)
    mask = np.ones((h, w), dtype=np.float32)

    # Vertical borders
    for i in range(border_h):
        factor = darkening + (1 - darkening) * (i / border_h)
        mask[i, :] *= factor
        mask[h - 1 - i, :] *= factor

    # Horizontal borders
    for j in range(border_w):
        factor = darkening + (1 - darkening) * (j / border_w)
        mask[:, j] *= factor
        mask[:, w - 1 - j] *= factor

    # Apply mask
    if len(result.shape) == 3:
        result *= mask[:, :, np.newaxis]
    else:
        result *= mask

    return np.clip(result, 0, 255).astype(np.uint8)


def apply_zone_darkening(frame: np.ndarray, target_apl: float = 25,
                         zone_size: int = 64) -> np.ndarray:
    """Selectively darken bright zones to hit target APL.

    Divides the frame into zones and preferentially darkens the brightest
    zones that contribute most to APL, starting with least-salient areas.

    Args:
        frame: Input BGR frame
        target_apl: Target APL percentage
        zone_size: Size of each zone in pixels
    """
    current_apl = calculate_apl(frame)
    if current_apl <= target_apl:
        return frame

    result = frame.copy().astype(np.float32)
    h, w = frame.shape[:2]

    # Divide into zones and calculate per-zone APL
    zones = []
    for y in range(0, h, zone_size):
        for x in range(0, w, zone_size):
            y_end = min(y + zone_size, h)
            x_end = min(x + zone_size, w)
            zone = result[y:y_end, x:x_end]
            zone_apl = calculate_apl(zone.astype(np.uint8))
            # Saliency heuristic: edges and center are more important
            dist_from_center = np.sqrt(
                ((y + zone_size // 2 - h // 2) / h) ** 2
                + ((x + zone_size // 2 - w // 2) / w) ** 2
            )
            saliency = 1.0 - dist_from_center  # Center = high saliency
            zones.append({
                "y": y, "x": x, "y_end": y_end, "x_end": x_end,
                "apl": zone_apl, "saliency": saliency,
            })

    # Sort by saliency (low first = darken these first)
    zones.sort(key=lambda z: z["saliency"])

    # Iteratively darken zones until target APL is reached
    reduction_factor = 0.95  # Reduce by 5% each iteration
    for _ in range(50):  # Max iterations
        current_apl = calculate_apl(result.astype(np.uint8))
        if current_apl <= target_apl:
            break

        for zone in zones:
            if current_apl <= target_apl:
                break
            region = result[zone["y"]:zone["y_end"], zone["x"]:zone["x_end"]]
            zone_apl = calculate_apl(region.astype(np.uint8))
            if zone_apl > target_apl * 0.5:  # Only darken bright zones
                result[zone["y"]:zone["y_end"], zone["x"]:zone["x_end"]] *= reduction_factor
                current_apl = calculate_apl(result.astype(np.uint8))

    return np.clip(result, 0, 255).astype(np.uint8)


def process_video(input_path: str, output_path: str, strategy: str = "highlight",
                  target_apl: float = 25, **kwargs):
    """Process a video file, applying APL reduction to each frame."""
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"Error: Cannot open {input_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    strategies = {
        "highlight": lambda f: apply_highlight_compression(f, **kwargs),
        "border": lambda f: apply_border_darkening(f, **kwargs),
        "zone": lambda f: apply_zone_darkening(f, target_apl=target_apl, **kwargs),
    }

    apply_fn = strategies.get(strategy)
    if not apply_fn:
        print(f"Unknown strategy: {strategy}. Use: {list(strategies.keys())}")
        return

    frame_num = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        original_apl = calculate_apl(frame)
        processed = apply_fn(frame)
        new_apl = calculate_apl(processed)

        out.write(processed)
        frame_num += 1

        if frame_num % 100 == 0:
            print(
                f"Frame {frame_num}/{total_frames} | "
                f"APL: {original_apl:.1f}% -> {new_apl:.1f}%"
            )

    cap.release()
    out.release()
    print(f"\nProcessed {frame_num} frames -> {output_path}")


def main():
    parser = argparse.ArgumentParser(description="APL Reducer — ABL mitigation via content modification")
    parser.add_argument("input", help="Input video file")
    parser.add_argument("output", help="Output video file")
    parser.add_argument(
        "--strategy", default="highlight",
        choices=["highlight", "border", "zone"],
        help="APL reduction strategy (default: highlight)"
    )
    parser.add_argument("--target-apl", type=float, default=25, help="Target APL %% (default: 25)")
    parser.add_argument("--threshold", type=float, default=90, help="Highlight threshold %% (default: 90)")
    parser.add_argument("--compression", type=float, default=0.7, help="Highlight compression (default: 0.7)")
    parser.add_argument("--border-pct", type=float, default=5, help="Border width %% (default: 5)")
    parser.add_argument("--darkening", type=float, default=0.85, help="Border darkening (default: 0.85)")
    args = parser.parse_args()

    kwargs = {}
    if args.strategy == "highlight":
        kwargs = {"threshold_pct": args.threshold, "compression": args.compression}
    elif args.strategy == "border":
        kwargs = {"border_pct": args.border_pct, "darkening": args.darkening}

    process_video(args.input, args.output, args.strategy, args.target_apl, **kwargs)


if __name__ == "__main__":
    main()
