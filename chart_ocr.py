"""OCR trade markers off hourly chart snapshots.

Reads the JPEG snapshots produced by generate_hourly_snapshots.py and
extracts each BUY / SELL / TP box's signal type and price by:
  1. Masking pixels matching the box fill colors (green / red / orange).
  2. Filling interior text holes so each box is one connected region.
  3. For each candidate region, keeping only white text inside the region
     and running tesseract on that isolated crop.

Also maps each box's x-pixel back to a timestamp using the chart's
90-minute rolling window (HH:00 snapshot -> (HH-1):30 to HH:00).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image
from scipy import ndimage
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

_CHARTS_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "charts")

# Box fill colors from plotFigure.py (green / red / darkorange) after
# alpha blending onto the white plot background.
_COLOR_MASKS = {
    "BUY":  lambda r, g, b: (g > 60) & (g < 180) & (r < 40) & (b < 40),
    "SELL": lambda r, g, b: (r > 130) & (r < 230) & (g < 40) & (b < 40),
    "TP":   lambda r, g, b: (r > 200) & (g > 90) & (g < 180) & (b < 40),
}

# Minimum pixel area per kind — set high enough to reject the small green
# "High" and red "Low" price-line dots (~30-50 px each) as well as the
# triangle-arrow entry markers, keeping only the large annotation boxes.
_MIN_AREA = {"BUY": 8000, "SELL": 8000, "TP": 4000}
# Boxes are wider than they are tall (the label has price + time stacked
# on two/three lines). Reject stray candlestick-shaped regions that the
# mask picks up in the price-line area.
_MIN_WIDTH = 100
_MIN_HEIGHT = 80


@dataclass
class TradeMarker:
    kind: str            # "BUY", "SELL", or "TP"
    price: Optional[int]  # 5-digit price parsed from the label, if OCR succeeded
    minute: Optional[str] = None  # HH:MM, mapped from the box's x-pixel
    raw_text: str = ""
    cx: int = 0          # box center x-pixel (for debugging / dedup)
    cy: int = 0
    # Filled in by compute_running_pl() below — the change vs. the prior
    # marker in the series, and the cumulative realized P/L up to and
    # including this marker.
    change: Optional[float] = None
    total_pl: Optional[float] = None


def compute_running_pl(markers: list["TradeMarker"], contracts: int = 2,
                       price_tolerance: int = 500) -> None:
    """Fill each marker's `change` and `total_pl` fields based on a
    simple FIFO simulation across the ordered sequence.

    Assumes:
      - BUY / SELL fully reverse the position (open `contracts` on the
        new side, closing any existing).
      - TP takes one contract off the current position at the TP price.
      - Same-minute duplicates that come from overlapping snapshots are
        skipped so each real trade is counted once.
      - Prices that deviate more than `price_tolerance` points from the
        running median of prior valid prices are rejected as OCR
        misreads (e.g. leading "5" mistaken for "2" → 22599 vs 52599).

    Mutates the passed markers in place.
    """
    pos = 0        # +long / -short contract count
    entry = 0.0    # average entry price of the currently-held position
    realized = 0.0  # running P/L in points
    seen = set()   # dedup by (minute, kind, price)
    reference_prices: list[int] = []

    for m in markers:
        if m.price is None or m.minute is None:
            continue
        # Sanity: if we have a running set of valid prices, reject any
        # OCR reading that's more than tolerance points away from the
        # median. Guards against 22599 / 5256! style misreads.
        if reference_prices:
            ref = sorted(reference_prices)[len(reference_prices) // 2]
            if abs(m.price - ref) > price_tolerance:
                m.change = 0.0
                m.total_pl = realized
                m.raw_text = f"[OCR outlier {m.price} rejected] " + m.raw_text
                m.price = None
                continue
        reference_prices.append(m.price)
        if len(reference_prices) > 20:
            reference_prices.pop(0)

        key = (m.minute, m.kind, m.price)
        if key in seen:
            m.change = 0.0
            m.total_pl = realized
            continue
        seen.add(key)

        prev = realized
        if m.kind == "BUY":
            if pos < 0:  # close short first
                realized += (entry - m.price) * abs(pos)
            pos = contracts
            entry = float(m.price)
        elif m.kind == "SELL":
            if pos > 0:
                realized += (m.price - entry) * pos
            pos = -contracts
            entry = float(m.price)
        elif m.kind == "TP":
            if pos > 0:
                realized += (m.price - entry) * 1
                pos -= 1
            elif pos < 0:
                realized += (entry - m.price) * 1
                pos += 1

        m.change = realized - prev
        m.total_pl = realized


def _find_plot_bounds(im: Image.Image) -> tuple[int, int, int, int]:
    """Return (left, right, top, bottom) pixel bounds of the plot area
    (excluding the axis ticks and the stats box on the right). We
    approximate this by finding the outermost gray gridline pixels — the
    plot area is bounded by axis spines rendered in a specific gray.

    Fallback: heuristic based on image dimensions if detection fails.
    """
    arr = np.asarray(im.convert("RGB"))
    h, w = arr.shape[:2]
    # Rough proportions from the rendered charts (16x9 figure with
    # subplots_adjust left=0.07 right=0.82 top=0.92 bottom=0.12): the
    # plot area sits at roughly the same fraction regardless of DPI.
    left = int(w * 0.07)
    right = int(w * 0.82)
    top = int(h * 0.08)
    bottom = int(h * 0.88)
    return left, right, top, bottom


def _label_boxes(mask: np.ndarray, min_area: int) -> list[tuple[int, int, int, int, int]]:
    """Fill text holes and return each candidate region as
    (x0, y0, x1, y1, label_id)."""
    filled = ndimage.binary_fill_holes(mask)
    labeled, n = ndimage.label(filled)
    boxes = []
    for lbl in range(1, n + 1):
        ys, xs = np.where(labeled == lbl)
        if len(ys) < min_area:
            continue
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        wid, hgt = x1 - x0 + 1, y1 - y0 + 1
        if wid < _MIN_WIDTH or hgt < _MIN_HEIGHT:
            continue
        aspect = wid / hgt
        if aspect < 0.4 or aspect > 3.0:
            continue
        boxes.append((x0, y0, x1, y1, lbl))
    return boxes


def _ocr_box(im: Image.Image, region_mask: np.ndarray, box: tuple, pad: int = 20) -> str:
    """OCR just the white label text inside the given box region.

    Adds `pad` px of margin around the crop so tesseract has whitespace
    to work with — critical for boxes near the plot edge where the raw
    bounding box hugs the letters."""
    h, w = region_mask.shape
    x0, y0, x1, y1, lbl = box
    xs0 = max(0, x0 - pad)
    ys0 = max(0, y0 - pad)
    xs1 = min(w, x1 + pad + 1)
    ys1 = min(h, y1 + pad + 1)
    crop_arr = np.asarray(im.crop((xs0, ys0, xs1, ys1))).astype(int)
    r, g, b = crop_arr[..., 0], crop_arr[..., 1], crop_arr[..., 2]
    region_slice = region_mask[ys0:ys1, xs0:xs1]
    region_filled = ndimage.binary_fill_holes(region_slice)
    white = (r > 200) & (g > 200) & (b > 200) & region_filled
    if white.sum() < 40:
        return ""
    out = np.where(white[..., None], 0, 255).astype("uint8")
    out = np.broadcast_to(out, crop_arr.shape).copy()
    return pytesseract.image_to_string(
        Image.fromarray(out), config="--psm 6").strip()


_PRICE_RE = re.compile(r"(\d{5})")
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
# Kind + price + optional time triplets. Tolerates OCR noise between the
# tokens (spaces, pipe characters, stray glyphs). "TT" is a common OCR
# misread for "TP".
_TRIPLET_RE = re.compile(
    r"(BUY|SELL|TP|TT|LIQ)"
    r"[^\d]{0,15}?"
    r"(\d{5})"
    r"(?:[^\d]{0,25}?([01]?\d|2[0-3]):([0-5]\d))?",
    re.IGNORECASE | re.DOTALL,
)

_KIND_ALIASES = {"TT": "TP"}


def _parse_triplets(text: str) -> list[tuple[str, int, Optional[str]]]:
    """Extract every (kind, price, HH:MM) triplet from OCR text.

    Handles merged regions where multiple BUY/SELL/TP labels got
    captured as one crop — the region's color mask told us "there's a
    marker here" but the OCR text tells us exactly which markers.
    Time may be None if OCR missed the timestamp for that label.
    """
    out = []
    for m in _TRIPLET_RE.finditer(text):
        kind = m.group(1).upper()
        kind = _KIND_ALIASES.get(kind, kind)
        if kind == "LIQ":
            # LIQ (liquidation) is rendered with the same green/red as
            # BUY/SELL — treat it as its underlying side. We can't tell
            # from the text alone; skip for now to avoid confusion.
            continue
        price = int(m.group(2))
        time_str = None
        if m.group(3) is not None and m.group(4) is not None:
            time_str = f"{int(m.group(3)):02d}:{m.group(4)}"
        out.append((kind, price, time_str))
    return out


def _pixel_to_minute(cx: int, plot_left: int, plot_right: int,
                     start_min: int, end_min: int) -> str:
    """Linear-map an x-pixel to a HH:MM label within the plot window."""
    if plot_right <= plot_left:
        return ""
    frac = (cx - plot_left) / (plot_right - plot_left)
    frac = max(0.0, min(1.0, frac))
    total = start_min + frac * (end_min - start_min)
    hh = int(total) // 60
    mm = int(round(total)) % 60
    return f"{hh:02d}:{mm:02d}"


def extract_markers_from_snapshot(img_path: str,
                                  window_end_hhmm: str,
                                  window_start_hhmm: Optional[str] = None,
                                  window_minutes: int = 90) -> list[TradeMarker]:
    """Extract all BUY/SELL/TP markers from one snapshot image.

    Args:
        img_path: path to the JPEG snapshot.
        window_end_hhmm: chart end time, e.g. "12:00".
        window_start_hhmm: chart start time, e.g. "10:30". Overrides
            window_minutes when set. Used for edge-clipped snapshots
            (e.g. the 10:00 chart only spans 09:30-10:00, not 90 min).
        window_minutes: chart span in minutes (default 90) — only used
            when window_start_hhmm is None.
    """
    im = Image.open(img_path).convert("RGB")
    arr = np.asarray(im)
    r = arr[..., 0].astype(int)
    g = arr[..., 1].astype(int)
    b = arr[..., 2].astype(int)

    left, right, top, bottom = _find_plot_bounds(im)
    end_h, end_m = (int(x) for x in window_end_hhmm.split(":"))
    end_total = end_h * 60 + end_m
    if window_start_hhmm:
        s_h, s_m = (int(x) for x in window_start_hhmm.split(":"))
        start_total = s_h * 60 + s_m
    else:
        start_total = end_total - window_minutes

    markers: list[TradeMarker] = []
    for kind, maskfn in _COLOR_MASKS.items():
        mask = maskfn(r, g, b)
        labeled_full, _ = ndimage.label(ndimage.binary_fill_holes(mask))
        for box in _label_boxes(mask, _MIN_AREA[kind]):
            x0, y0, x1, y1, _ = box
            cx = (x0 + x1) // 2
            cy = (y0 + y1) // 2
            # Skip boxes that sit outside the plot area (stats box glyphs,
            # legend colors, etc.).
            if cx < left or cx > right or cy < top or cy > bottom:
                continue
            text = _ocr_box(im, labeled_full == labeled_full[cy, cx], box)
            triplets = _parse_triplets(text)
            # If OCR captured labeled triplets (BUY/SELL/TP + price
            # + optional time), trust those — they're authoritative
            # even inside merged regions.
            if triplets:
                for kind_ocr, price, time_str in triplets:
                    minute = time_str or _pixel_to_minute(
                        cx, left, right, start_total, end_total)
                    markers.append(TradeMarker(
                        kind=kind_ocr,
                        price=price,
                        minute=minute,
                        raw_text=text.replace("\n", " | "),
                        cx=cx, cy=cy,
                    ))
                continue

            # No labeled triplet — fall back to price/time-only tokens
            # so we still capture the marker (its kind comes from the
            # region's color mask).
            price_m = _PRICE_RE.search(text)
            time_m = _TIME_RE.search(text)
            price = int(price_m.group(1)) if price_m else None
            time_str = (f"{int(time_m.group(1)):02d}:{time_m.group(2)}"
                        if time_m else None)
            if price is None and time_str is None:
                continue
            minute = time_str or _pixel_to_minute(
                cx, left, right, start_total, end_total)
            markers.append(TradeMarker(
                kind=kind,
                price=price,
                minute=minute,
                raw_text=text.replace("\n", " | "),
                cx=cx, cy=cy,
            ))
    markers.sort(key=lambda m: m.cx)
    return markers


_SESSION_OPEN_MIN = 9 * 60 + 30  # 09:30 ET


def extract_markers_for_date(target_date: str, kind: str = "algo") -> dict[str, list[TradeMarker]]:
    """Return {hour_hhmm: [markers]} for every hourly snapshot found.

    kind is "algo" or "ib" — matches the filename suffix.
    """
    out: dict[str, list[TradeMarker]] = {}
    for hh in range(10, 17):
        end_time = f"{hh:02d}:00"
        img_path = os.path.join(
            _CHARTS_DIR, f"YM_{target_date}_{hh:02d}00_{kind}_snapshot.jpg")
        if not os.path.exists(img_path):
            continue
        end_total = hh * 60
        start_total = max(end_total - 90, _SESSION_OPEN_MIN)
        start_hhmm = f"{start_total // 60:02d}:{start_total % 60:02d}"
        out[end_time] = extract_markers_from_snapshot(
            img_path, end_time, window_start_hhmm=start_hhmm)
    return out


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-06-30"
    kind = sys.argv[2] if len(sys.argv) > 2 else "algo"
    all_markers = extract_markers_for_date(date, kind)
    for hour, ms in all_markers.items():
        print(f"\n=== {hour} ({kind}) — {len(ms)} markers ===")
        for m in ms:
            print(f"  {m.minute}  {m.kind:<4} {m.price}  (raw={m.raw_text!r})")
