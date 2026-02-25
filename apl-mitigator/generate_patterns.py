#!/usr/bin/env python3
"""Generate APL test pattern images for ABL profiling."""

import sys

import numpy as np

try:
    import cv2
except ImportError:
    print("OpenCV required: pip install opencv-python")
    sys.exit(1)


def generate_apl_pattern(width: int, height: int, apl_pct: int,
                         pattern_type: str = "horizontal") -> np.ndarray:
    """Generate a test pattern image with a specific APL level.

    Args:
        width: Image width
        height: Image height
        apl_pct: Target APL percentage (0-100)
        pattern_type: How to distribute the white area
            - "horizontal": White rows from top
            - "centered": White rectangle centered
            - "checker": Checkerboard pattern at target duty cycle
    """
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    if pattern_type == "horizontal":
        white_rows = int(height * apl_pct / 100)
        frame[:white_rows, :] = 255

    elif pattern_type == "centered":
        # Calculate centered rectangle dimensions for target APL
        target_area = width * height * apl_pct / 100
        aspect = width / height
        rect_h = int(np.sqrt(target_area / aspect))
        rect_w = int(rect_h * aspect)
        y_start = (height - rect_h) // 2
        x_start = (width - rect_w) // 2
        frame[y_start:y_start + rect_h, x_start:x_start + rect_w] = 255

    elif pattern_type == "checker":
        # Checkerboard with block size adjusted for target APL
        block_size = 16
        for y in range(0, height, block_size):
            for x in range(0, width, block_size):
                block_idx = (y // block_size + x // block_size)
                # Use threshold to achieve target APL
                if (block_idx % 100) < apl_pct:
                    y_end = min(y + block_size, height)
                    x_end = min(x + block_size, width)
                    frame[y:y_end, x:x_end] = 255

    return frame


def main():
    width, height = 3840, 2160
    apl_levels = [1, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]
    pattern_types = ["horizontal", "centered"]

    for pattern_type in pattern_types:
        for apl in apl_levels:
            frame = generate_apl_pattern(width, height, apl, pattern_type)
            actual_apl = frame.mean() / 255 * 100
            filename = f"pattern_{pattern_type}_apl{apl:03d}.png"
            cv2.imwrite(filename, frame)
            print(f"  {filename} (target APL: {apl}%, actual: {actual_apl:.1f}%)")

    print(f"\nGenerated {len(apl_levels) * len(pattern_types)} test patterns")
    print("Display these on the TV and measure brightness of the white area")
    print("to characterize the ABL curve.")


if __name__ == "__main__":
    main()
