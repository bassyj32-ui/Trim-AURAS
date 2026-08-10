"""Check yt-dlp extractors available."""
import yt_dlp
from yt_dlp.extractor import gen_extractor_classes

print(f"yt-dlp version: {yt_dlp.version.__version__}")
names = []
for cls in gen_extractor_classes():
    names.append(cls.__name__)

# Search for anything frame or drive related
print("\n=== Frame/Drive related extractors ===")
for n in names:
    low = n.lower()
    if 'frame' in low:
        print(f"  {n}")
if not any('frame' in n.lower() for n in names):
    print("  (no Frame.io extractor found)")

for n in names:
    if 'googledrive' in n.lower() or 'drive' in n.lower():
        print(f"  {n}")

print(f"\nTotal extractors: {len(names)}")
