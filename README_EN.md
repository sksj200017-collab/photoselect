# PhotoSelect · Photo Picker — by nfd 📷

> **English** | [中文](README.md)

> Not Photoshop — PhotoSelect! A tiny tool to help you "declutter" your photo collection.

Shot 800 photos on a burst but only want 10? PhotoSelect automatically groups near-identical photos together, so you can compare them side by side, keep the best one or two from each group, and move the rest away in one click. Nothing is ever truly deleted — you can always change your mind.

**Current version: v1.0.1** · Windows · No installation needed — just double-click to run

## 📥 Download

- **GitHub Releases (always the latest)**: https://github.com/sksj200017-collab/photoselect/releases/latest
- Download `PhotoSelect.exe` and double-click it — that's it.
- What's new in each release: see `CHANGELOG.md`

## ✨ Why photographers will love it

- **Large-photo review**: dark interface, photos maximized to fill the screen — the photos are the star, not the buttons
- **One click = one choice**: click a photo to toggle Keep ✓ / Discard ✗; keyboard works too — ←/→ to switch groups, Enter to confirm
- **Burst-mode lifesaver (Strict Dedup)**: hundreds of burst shots auto-grouped — keep only the best frames
- **Portrait picker (Same-Subject Mode)**: offline AI groups photos of the **same person in the same scene** together — it matches both the face and the background, and correctly splits different people
- **Blurry-photo detective**: auto-detects out-of-focus and camera-shake shots, recommends keeping the sharp one
- **Later-shot priority**: within each group it recommends keeping the photo with the latest capture time (the later burst frames usually have the best expressions)
- **JPG + RAW managed together**: Nikon NEF, Canon CR2/CR3, Sony ARW, Fuji RAF… RAW and its paired JPG move together, never separated
- **100% offline**: your photos never leave your computer — face recognition runs locally too; no ads, no uploads

## 🚀 Quick start (30 seconds)

1. Double-click `PhotoSelect.exe` — no installation needed
2. Click "Select Folder" and pick the folder of photos to organize
3. Choose file type (All / JPG only / RAW only) and analysis mode (burst shooting → "Strict Dedup"; portraits → "Same-Subject Mode"); **enable "Blur Detection" if you also want blurry shots flagged**
4. Click "Start Analysis", then review the groups in the Group Overview — drag photos between groups if you want to adjust
5. Large-photo review: **click a photo = keep ✓**, click "Confirm Group" to move to the next one; when all groups are done, click "Export"

Discarded photos are never deleted — they are moved into a `待删除` (to-delete) folder inside your original folder. Manually empty it once you are satisfied.

## ✅ When to use it

- **Events / travel / burst shooting**: pick the best few out of hundreds
- **Portrait selection**: pick the best expressions and compositions from N shots of the same person in the same scene
- **Photo dedup**: repeated scenes, copied files, duplicate downloads
- **Supported formats**: JPG, major RAW formats (NEF / CR2 / CR3 / ARW / DNG / RAF / RW2 / ORF / PEF / SRW / X3F / ERF), iPhone HEIC / HEIF

## ⚠️ Notes

- **Windows only** (no macOS version planned)
- **Blur detection has limits**: very mild softness ("not quite tack-sharp") and true focus misses cannot always be told apart — **workaround**: you always have the final say; one click flips a photo between keep/discard, and if you actually want that dreamy soft look, just click Keep
- **Extreme compositions may not auto-group**: a close-up big face vs. a distant tiny person — **workaround**: drag them into the same group manually in the Group Overview, takes seconds
- **Large folders (thousands of photos)**: first analysis takes a few minutes — that's normal (≈300 photos in about 10 seconds)
- **Antivirus false positives**: some antivirus tools may flag packaged tools — add an exception; this software is fully offline and never connects to the network

## 💬 FAQ

- **Can I recover "deleted" photos?** Yes. Photos in the `待删除` (to-delete) folder are only **moved**, not deleted; or click "↩ Undo Group" inside the app to restore them automatically.
- **Which cameras and formats are supported?** Major RAW formats from Nikon, Canon, Sony, Fuji, Panasonic, Sigma etc. (NEF / CR2 / CR3 / ARW / DNG / RAF / RW2 / ORF / PEF / SRW / X3F / ERF), JPG, and iPhone HEIC / HEIF.
- **Are my photos uploaded anywhere?** No. The app runs fully offline — face recognition is processed on your own machine, and your photos never leave your computer.

## 🛡 Safety & privacy

- Fully offline — **no network access, no photo or face-data uploads**
- Moves instead of deletes — every action is undoable and recoverable
- Back up important photos first, especially the first time you process a large folder

## 📜 License

- ✅ **Free for personal use** — feel free to share it with friends (non-commercial)
- ⛔ **No commercial use**; do not remove or alter the copyright attribution (by nfd)
- 📮 For commercial use or collaboration, contact the author: **745936837@qq.com** / WeChat **13917034098**
- 📖 Full terms in the `LICENSE` file

## 🐛 Found a bug?

Please include: the software version (visible in the "About" dialog), a screenshot, and the steps that led to the problem.

- Email: **745936837@qq.com**
- WeChat: **13917034098**

## 🛠 How it came to be

The author, nfd, is a **psychology graduate who doesn't know how to code**. PhotoSelect was "talked into existence" with an AI assistant (vibecoding — telling an AI in plain language what to build): it started from a single sentence — "I want a tool to pick photos" — and grew through a dozen iterations into what you see today.

**An ordinary person with no coding skills can build a genuinely useful piece of software with an idea and AI** — that's what PhotoSelect is here to prove. If you think building software with AI is cool, give it a try.

Found a bug or have a question? **Your feedback is very welcome** — every report makes it better: [contact info above](#-found-a-bug).
