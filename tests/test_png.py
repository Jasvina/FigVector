from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from figvector.models import RasterImage
from figvector.png import read_png, write_png


class PNGRoundTripTests(unittest.TestCase):
    def test_round_trip_rgba_png(self) -> None:
        image = RasterImage(
            width=3,
            height=2,
            pixels=[
                [(255, 255, 255, 255), (10, 20, 30, 255), (1, 2, 3, 128)],
                [(100, 90, 80, 255), (7, 8, 9, 255), (40, 50, 60, 255)],
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "roundtrip.png"
            write_png(path, image)
            loaded = read_png(path)

        self.assertEqual(image.width, loaded.width)
        self.assertEqual(image.height, loaded.height)
        self.assertEqual(image.pixels, loaded.pixels)


if __name__ == "__main__":
    unittest.main()
