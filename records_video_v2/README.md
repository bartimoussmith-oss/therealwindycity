# How the records are collected

Fresh standalone video project. No imports from the earlier provenance package, no PR #26 merge, and no changes to the live site.

The workflow builds wide and phone-sized silent process guides, seven individual chapter clips per format, a playable HTML page, and a machine-readable report. Counts describe files in three named folders in the checkout, not unique meetings or complete coverage. It does not collect new records or prove that a collection session occurred.

Run locally with Python 3.11, Pillow 11.3.0, ffmpeg/ffprobe, and DejaVu fonts: `python records_video_v2/build.py --format wide`.

GitHub starts the build when these project files change on main. Manual reruns are available through Fresh records videos in Actions. Each build fully decodes its MP4s and checks duration, dimensions, and chapter bounds. Download its artifact and open index.html. Results are retained for 14 days, not deployed live.
