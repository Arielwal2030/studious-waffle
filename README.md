# DailyMindShift: YouTube Shorts pipeline

This turns short mindset scripts into ready-to-post YouTube Shorts. Each video is vertical (1080×1920) with a free AI voiceover, captions timed to the voice, and your channel handle on screen. It can also upload one Short a day for you.

It comes with **10 finished scripts** in the `scripts` folder.

**Channel name ideas** (check that the name is free on YouTube first): **DailyMindShift**, One Minute Mindset, Quiet Mind Daily, The Inner Reset, Shift Your Thinking. To use a different name, change `channel_name` in `config.json`.

---

## Setup (about 30 minutes, once)

You need a Windows, Mac or Linux computer. It won't run on a phone.

### 1. Install Python
Download Python 3.10 or newer from [python.org/downloads](https://www.python.org/downloads/).
**Windows:** on the first install screen, tick **"Add python.exe to PATH"**.

### 2. Download this project
On the GitHub page, click **Code → Download ZIP**, then unzip it somewhere easy to find, like your Desktop.

### 3. Install the parts it needs
Open a terminal in the project folder:
- **Windows:** open the folder, click the address bar, type `cmd` and press Enter
- **Mac:** right-click the folder and choose **New Terminal at Folder**

Then run:
```
pip install -r requirements.txt
```
(On a Mac, use `pip3` and `python3` everywhere this guide says `pip` and `python`.)

### 4. Make your first videos
```
python shorts.py build
```
This makes all 10 videos in the `output` folder. It takes a few minutes and needs an internet connection for the voice. Each video comes with a `.txt` file holding its title, description and tags, ready to copy and paste.

Watch one before you post anything.

---

## Posting

### Option A: upload by hand (recommended to start)
Open [YouTube Studio](https://studio.youtube.com), click **Create → Upload videos**, and drag in a week of videos at once. For each video, paste in the title and description from its `.txt` file, then set **Visibility → Schedule** to one per day. It takes about 10 minutes a week.

### Option B: automatic daily uploads
> **Heads up:** Google locks videos uploaded through a new API project as **private** until the project passes a free audit ([request one here](https://support.google.com/youtube/contact/yt_api_form)). Until then, automatic uploads won't be visible to anyone, so use Option A.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project.
2. Under **APIs & Services → Library**, search for **YouTube Data API v3** and click **Enable**.
3. Under **Google Auth Platform** (also called **OAuth consent screen**), set it up as **External** and add your own Google account as a **test user**.
4. Under **Clients**, choose **Create client → Desktop app**, then download the JSON file. Rename it `client_secret.json` and put it in this folder.
5. Run `python shorts.py upload-next`. A browser window opens. Sign in with the Google account that owns your channel. This posts the first video.
6. To post one a day, run `python shorts.py schedule` and leave the window open. It posts at `post_time` in `config.json` (5 pm by default).

While your Google project is in "Testing" mode, the sign-in expires after 7 days, so you'll need to run `upload-next` and sign in again each week.

---

## Commands

| Command | What it does |
|---|---|
| `python shorts.py build` | Builds all the videos |
| `python shorts.py build 03` | Builds just the script whose filename starts with `03` |
| `python shorts.py status` | Shows which videos are built and which are posted |
| `python shorts.py upload-next` | Uploads the next video that hasn't been posted |
| `python shorts.py schedule` | Posts one a day, automatically |
| `python shorts.py prompt` | Prints a prompt for getting 10 new scripts from a free AI chatbot |
| `python shorts.py voices` | Lists voices you can choose from |

## Writing new scripts
Run `python shorts.py prompt` and paste the output into a free AI chatbot such as [claude.ai](https://claude.ai). Save each script it gives you as a `.txt` file in `scripts/`. Every script follows this format:
```
title: The 2-Minute Rule That Kills Procrastination
tags: procrastination, productivity, mindset
---
One sentence per line.
Another sentence.
```
**Always read and edit the scripts yourself.** Your own voice and ideas are what make the channel worth watching, and YouTube rewards that (see below).

## Making it look better (optional)
- **Backgrounds:** put `.jpg` or `.png` photos into a `backgrounds` folder. They'll be cropped and darkened automatically. Free sources include [Pexels](https://www.pexels.com) and [Unsplash](https://unsplash.com). Without photos, each video gets a color gradient.
- **Music:** put `.mp3` files into a `music` folder. It plays quietly under the voice. Only use music you have the rights to, such as the free [YouTube Audio Library](https://studio.youtube.com) (it's under **Audio library** in Studio).
- **Voice, speed, caption size, posting time:** change these in `config.json`.

## Your ClickBank link
Links in Shorts descriptions aren't clickable, so put your affiliate link on your **channel page**. Go to **YouTube Studio → Customization → Profile → Links**. Every description already says "Free guide on my channel page" and includes an affiliate disclosure. You can change both in `config.json`.

## Be realistic about the money
- **Nothing here guarantees income.** Most new channels grow slowly. Plan on posting daily for at least 2–3 months before deciding whether it works.
- **To join the YouTube Partner Program** and earn ad revenue, you need 1,000 subscribers plus 10 million Shorts views in 90 days, or 4,000 watch hours.
- **YouTube won't pay for "mass-produced" or repetitive content.** Channels that look like one template stamped out over and over get rejected. Write and edit your own scripts, vary your backgrounds, and consider recording your own voice later. That's the difference between a channel that gets monetized and one that doesn't.
- **Pick a ClickBank product you'd actually recommend.** Avoid anything with miracle claims, which can get your channel flagged.
