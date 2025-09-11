import os
import requests
import threading
import asyncio
import cloudscraper
import time
from pyromod import listen
from pyrogram import Client
from pyrogram import filters
from pyrogram.types import Message
from config import CHANNEL_ID, THUMB_URL, BOT_TEXT
from Extractor import app
from Extractor.core.utils import forward_to_log
import datetime

# Cloudscraper for requests
scraper = cloudscraper.create_scraper()

# Base URL for HLS videos (CloudFront)
# You can dynamically append the quality path like "360p/360p.m3u8"
CF_BASE_URL = "https://d14v4v80cpjht7.cloudfront.net/file_library/videos/migration/brightcove/"

# Function to get full HLS link
def get_hls_link(video_id, quality="360p"):
    """
    video_id: unique video folder name
    quality: '240p', '360p', '720p'
    """
    if quality not in ["240p", "360p", "720p"]:
        quality = "360p"
    return f"{CF_BASE_URL}{video_id}/{quality}/{quality}.m3u8"


# -------------------- Helper Functions ---------------------

def download_thumbnail(url):
    try:
        response = scraper.get(url)
        if response.status_code == 200:
            thumb_path = "thumb_temp.jpg"
            with open(thumb_path, "wb") as f:
                f.write(response.content)
            return thumb_path
        return None
    except:
        return None

async def careerdl(app, message, headers, batch_id, token, topic_ids, prog, batch_name):
    try:
        topic_list = topic_ids.split('&')
        total_topics = len(topic_list)
        current_topic_count = 0
        total_videos = 0
        total_notes = 0
        start_time = time.time()
        result_text = ""

        # Download thumbnail once
        thumb_path = download_thumbnail(THUMB_URL)

        for topic_id in topic_list:
            current_topic_count += 1
            # Fetch batch detail
            details_url = f"https://elearn.crwilladmin.com/api/v9/batch-detail/{batch_id}?topicId={topic_id}"
            response = scraper.get(details_url, headers=headers)
            data = response.json().get("data", {})
            classes = data.get("class_list", {}).get("classes", [])
            classes.reverse()

            # Fetch topic name
            topic_url = f"https://elearn.crwilladmin.com/api/v9/batch-topic/{batch_id}?type=class"
            topic_data = scraper.get(topic_url, headers=headers).json().get("data", {})
            topics = topic_data.get("batch_topic", [])
            current_topic_name = next((t["topicName"] for t in topics if str(t["id"]) == topic_id), "Unknown Topic")

            # Time metrics
            elapsed = time.time() - start_time
            avg_per_topic = elapsed / current_topic_count
            remaining_topics = total_topics - current_topic_count
            eta = avg_per_topic * remaining_topics
            elapsed_str = f"{int(elapsed//60)}m {int(elapsed%60)}s"
            eta_str = f"{int(eta//60)}m {int(eta%60)}s"

            # Update progress
            progress_msg = (
                "🔄 <b>Processing Large Batch</b>\n"
                f"├─ Subject: {current_topic_count}/{total_topics}\n"
                f"├─ Name: <code>{current_topic_name}</code>\n"
                f"├─ Topics: {current_topic_count}/{total_topics}\n"
                f"├─ Links: {total_videos + total_notes}\n"
                f"├─ Time: {elapsed_str}\n"
                f"└─ ETA: {eta_str}"
            )
            await prog.edit_text(progress_msg)

            # Process classes/videos
            for cls in classes:
                vid_id = cls.get('id')
                lesson_name = cls.get('lessonName')
                lesson_ext = cls.get('lessonExt')
                detail_url = f"https://elearn.crwilladmin.com/api/v9/class-detail/{vid_id}"
                lesson_data = scraper.get(detail_url, headers=headers).json().get('data', {}).get('class_detail', {})
                lesson_url = lesson_data.get('lessonUrl', '')

                video_link = None
                if lesson_ext == 'brightcove':
                    video_link = f"{bc_url}{lesson_url}/master.m3u8?bcov_auth={token}"
                elif lesson_ext == 'youtube':
                    video_link = f"https://www.youtube.com/embed/{lesson_url}"
                elif lesson_ext == 'non_drm':
                    video_link = lesson_url  # direct m3u8 non-DRM
                else:
                    continue

                if video_link:
                    total_videos += 1
                    result_text += f"{lesson_name}: {video_link}\n"

            # Process notes
            notes_url = f"https://elearn.crwilladmin.com/api/v9/batch-topic/{batch_id}?type=notes"
            notes_resp = scraper.get(notes_url, headers=headers).json()
            for topic in notes_resp.get('data', {}).get('batch_topic', []):
                t_id = topic.get('id')
                notes_topic_url = f"https://elearn.crwilladmin.com/api/v9/batch-notes/{batch_id}?topicId={t_id}"
                notes_data = scraper.get(notes_topic_url, headers=headers).json()
                for note in reversed(notes_data.get('data', {}).get('notesDetails', [])):
                    doc_title = note.get('docTitle', '')
                    doc_url = note.get('docUrl', '').replace(' ', '%20')
                    line = f"{doc_title}: {doc_url}\n"
                    if line not in result_text:
                        result_text += line
                        total_notes += 1

        # Save results
        file_name = f"{batch_name.replace('/', '')}.txt"
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(result_text)

        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        caption = (
            "🎓 <b>COURSE EXTRACTED</b> 🎓\n\n"
            "📱 <b>APP:</b> CareerWill\n"
            f"📚 <b>BATCH:</b> {batch_name}\n"
            f"📅 <b>DATE:</b> {current_date} IST\n\n"
            "📊 <b>CONTENT STATS</b>\n"
            f"├─ 🎬 Videos: {total_videos}\n"
            f"├─ 📄 PDFs/Notes: {total_notes}\n"
            f"└─ 📦 Total Links: {total_videos + total_notes}\n\n"
            f"🚀 <b>Extracted by:</b> @{(await app.get_me()).username}\n\n"
            f"<code>╾───• {BOT_TEXT} •───╼</code>"
        )

        # Send results
        await app.send_document(message.chat.id, document=file_name, caption=caption, thumb=thumb_path if thumb_path else None)
        await app.send_document(CHANNEL_ID, document=file_name, caption=caption, thumb=thumb_path if thumb_path else None)

    finally:
        await prog.delete()
        if os.path.exists(file_name):
            os.remove(file_name)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

# -------------------- Command Handler ---------------------

@app.on_message(filters.command("ugcw") & filters.private)
async def career_will(app: Client, message: Message):
    try:
        welcome_msg = (
            "🔹 <b>C--W EXTRACTOR</b> 🔹\n\n"
            "Send <b>ID & Password</b> in this format: <code>ID*Password</code>\n\n"
            "<b>Example:</b>\n"
            "- ID*Pass: <code>6969696969*password123</code>\n"
            "- Token: <code>eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...</code>"
        )
        input1 = await app.ask(message.chat.id, welcome_msg)
        await forward_to_log(input1, "Careerwill Extractor")
        raw_text = input1.text.strip()

        if "*" in raw_text:
            email, password = raw_text.split("*")
            headers = {
                "Host": "elearn.crwilladmin.com",
                "appver": "107",
                "apptype": "android",
                "cwkey": "+HwN3zs4tPU0p8BpOG5ZlXIU6MaWQmnMHXMJLLFcJ5m4kWqLXGLpsp8+2ydtILXy",
                "content-type": "application/json; charset=UTF-8",
                "accept-encoding": "gzip",
                "user-agent": "okhttp/5.0.0-alpha.2"
            }
            data = {
                "deviceType": "android",
                "password": password,
                "deviceModel": "Xiaomi M2007J20CI",
                "deviceVersion": "Q(Android 10.0)",
                "email": email,
                "deviceIMEI": "d57adbd8a7b8u9i9",
                "deviceToken": "fake_device_token"
            }

            login_url = "https://wbspec.crwilladmin.com/api/v1/login"
            response = scraper.post(login_url, headers=headers, json=data)
            token = response.json()["data"]["token"]
            success_msg = (
                "✅ <b>CareerWill Login Successful</b>\n\n"
                f"🆔 <b>Credentials:</b> <code>{email}*{password}</code>"
            )
            await message.reply_text(success_msg)
        else:
            token = raw_text

        # Fetch Batches
        headers = {
            "Host": "elearn.crwilladmin.com",
            "appver": "107",
            "apptype": "android",
            "usertype": "2",
            "token": token,
            "cwkey": "+HwN3zs4tPU0p8BpOG5ZlXIU6MaWQmnMHXMJLLFcJ5m4kWqLXGLpsp8+2ydtILXy",
            "content-type": "application/json; charset=UTF-8",
            "accept-encoding": "gzip",
            "user-agent": "okhttp/5.0.0-alpha.2"
        }

        batch_url = "https://elearn.crwilladmin.com/api/v9/my-batch"
        response = scraper.get(batch_url, headers=headers)
        batches = response.json().get("data", {}).get("batchData", [])

        msg = "📚 <b>Available Batches</b>\n\n"
        for b in batches:
            msg += f"<code>{b['id']}</code> - <b>{b['batchName']}</b>\n"
        await message.reply_text(msg)

        input2 = await app.ask(message.chat.id, "<b>Send the Batch ID to download:</b>")
        raw_text2 = input2.text.strip()

        # Fetch Topics
        topic_url = f"https://elearn.crwilladmin.com/api/v9/batch-topic/{raw_text2}?type=class"
        topic_data = scraper.get(topic_url, headers=headers).json().get("data", {})
        topics = topic_data.get("batch_topic", [])
        batch_name = topic_data.get("batch_detail", {}).get("name", "Unknown Batch")

        id_list = ""
        topic_list_text = "📑 <b>Available Topics</b>\n\n"
        for topic in topics:
            topic_list_text += f"<code>{topic['id']}</code> - <b>{topic['topicName']}</b>\n"
            id_list += f"{topic['id']}&"

        await message.reply_text(topic_list_text)

        input3 = await app.ask(message.chat.id, 
            "📝 <b>Send topic IDs to download</b>\n\n"
            f"Format: <code>1&2&3</code>\n"
            f"All Topics: <code>{id_list}</code>"
        )
        raw_text3 = input3.text.strip()

        prog = await message.reply(
            "🔄 <b>Processing Content</b>\n\n"
            "├─ Status: Extracting content\n"
            "└─ Please wait..."
        )

        threading.Thread(target=lambda: asyncio.run(
            careerdl(app, message, headers, raw_text2, token, raw_text3, prog, batch_name)
        )).start()

    except Exception as e:
        error_msg = (
            "❌ <b>An error occurred</b>\n\n"
            f"Error details: <code>{str(e)}</code>\n\n"
            "Please try again or contact support."
        )
        await message.reply(error_msg)
