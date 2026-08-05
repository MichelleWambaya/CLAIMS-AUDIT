"""AAR Insurance Kenya brand constants — §9. Shared by every export
format so PPTX/PDF/XLSX all look like the same product family."""

COLOR_ORANGE = "F3781F"       # accent
COLOR_ORANGE_HOVER = "D9640F"
COLOR_BLACK = "1A1A1A"        # near-black text, not pure #000
COLOR_WHITE = "FFFFFF"
COLOR_GRAY_LIGHT = "F2F2F2"   # card backgrounds / zebra striping

FONT_HEADING = "Poppins"
FONT_BODY = "Inter"

# Fallbacks for environments without Poppins/Inter installed (export
# services should embed the fonts; this is a defensive default only).
FONT_HEADING_FALLBACK = "Calibri"
FONT_BODY_FALLBACK = "Calibri"
