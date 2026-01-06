# -*- coding: utf-8 -*-
import streamlit as st
import requests
import os
import time
import re
import concurrent.futures
from bs4 import BeautifulSoup
from streamlit.runtime.scriptrunner import add_script_run_ctx

# --- 基础配置 ---
st.set_page_config(page_title="NAS 漫画批量下载助手", page_icon="📚", layout="wide")

def clean_filename(filename):
    """清理非法字符，兼容 Win/Linux"""
    return re.sub(r'[\\/:*?"<>|]', '_', filename).strip()

def download_image(session, img_url, save_path, headers):
    """单图下载逻辑（带重试）"""
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        return True
    for _ in range(3):
        try:
            with session.get(img_url, stream=True, timeout=15, headers=headers) as r:
                if r.status_code == 200:
                    with open(save_path, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            f.write(chunk)
                    return True
        except:
            time.sleep(1)
    return False

def download_chapter_task(session, chapter_url, chapter_idx, title, headers, img_threads):
    """单章下载任务"""
    save_dir = os.path.join("downloads", title, f"{chapter_idx:03d}")
    os.makedirs(save_dir, exist_ok=True)

    try:
        res = session.get(chapter_url, timeout=15, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        img_tags = soup.find_all('img', class_='lazy')
        img_urls = [img['data-original'] for img in img_tags if img.has_attr('data-original')]

        if not img_urls:
            return "No Images"

        with concurrent.futures.ThreadPoolExecutor(max_workers=img_threads) as executor:
            for i, url in enumerate(img_urls, 1):
                executor.submit(download_image, session, url, os.path.join(save_dir, f"{i:03d}.jpg"), headers)
        return "SUCCESS"
    except Exception as e:
        return str(e)

def process_single_manga(session, target_url, chapter_threads, img_threads):
    """解析并下载单本漫画的核心逻辑"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...',
        'Referer': target_url
    }
    
    res = session.get(target_url, timeout=15, headers=headers)
    if res.status_code != 200:
        return None, "无法访问链接"
    
    soup = BeautifulSoup(res.text, 'html.parser')
    title_tag = soup.find('h1')
    if not title_tag:
        return None, "无法解析标题"
    
    title = clean_filename(title_tag.text.strip())
    links = soup.select('ul#detail-list-select li a')
    chapter_urls = ["https://mxs12.cc" + a['href'] for a in links]
    
    if not chapter_urls:
        return title, "未找到章节"

    # 执行章节并发下载
    with concurrent.futures.ThreadPoolExecutor(max_workers=chapter_threads) as executor:
        futures = []
        for i, c_url in enumerate(chapter_urls, 1):
            f = executor.submit(download_chapter_task, session, c_url, i, title, headers, img_threads)
            add_script_run_ctx(f)
            futures.append(f)
        
        # 实时监控章节完成情况（给进度条使用）
        yield title, len(chapter_urls), futures

# --- UI 界面 ---
st.title("📚 NAS 漫画全自动采集系统")
st.sidebar.header("并发参数设置")
c_threads = st.sidebar.slider("同时下载章节数", 1, 5, 2)
i_threads = st.sidebar.slider("每章并发图片数", 1, 10, 5)

tab1, tab2 = st.tabs(["🎯 单本下载", "批量全自动采集"])

# --- 模式1：单本下载 ---
with tab1:
    url_input = st.text_input("输入漫画目录页链接", placeholder="https://mxs12.cc/book/900")
    if st.button("立即开始"):
        if url_input:
            with requests.Session() as session:
                try:
                    gen = process_single_manga(session, url_input, c_threads, i_threads)
                    title, total_chapters, futures = next(gen)
                    st.write(f"正在下载：**{title}**")
                    pb = st.progress(0)
                    st_text = st.empty()
                    
                    done = 0
                    for f in concurrent.futures.as_completed(futures):
                        done += 1
                        pb.progress(done / total_chapters)
                        st_text.text(f"章节进度: {done}/{total_chapters}")
                    st.success(f"《{title}》下载完成！")
                except Exception as e:
                    st.error(f"发生错误: {e}")

# --- 模式2：批量采集 ---
with tab2:
    st.warning("提醒：批量下载会产生大量请求，请确保 NAS 空间充足，建议章节并发不要超过 2。")
    col1, col2 = st.columns(2)
    with col1:
        start_id = st.number_input("起始 ID (book/xxx)", value=900, min_value=1)
    with col2:
        end_id = st.number_input("结束 ID", value=905, min_value=1)

    if st.button("启动批量采集任务"):
        if start_id > end_id:
            st.error("起始 ID 必须小于结束 ID")
        else:
            main_pb = st.progress(0)
            main_status = st.empty()
            log_area = st.container()
            
            total_books = end_id - start_id + 1
            with requests.Session() as session:
                for idx, b_id in enumerate(range(start_id, end_id + 1)):
                    book_url = f"https://mxs12.cc/book/{b_id}"
                    main_status.markdown(f"**总体进度:** {idx}/{total_books} | **当前分析:** ID {b_id}")
                    
                    try:
                        gen = process_single_manga(session, book_url, c_threads, i_threads)
                        title, total_chapters, futures = next(gen)
                        
                        with log_area:
                            st.write(f"🚀 开始采集 ID {b_id}: 《{title}》...")
                            # 批量模式下，章节内部下载使用静默等待，不重复显示小进度条
                            concurrent.futures.wait(futures)
                            st.write(f"✅ 《{title}》下载成功。")
                        
                    except StopIteration:
                        st.write(f"⚠️ ID {b_id} 无效或无内容，已跳过。")
                    except Exception as e:
                        st.write(f"❌ ID {b_id} 出错: {e}")
                    
                    main_pb.progress((idx + 1) / total_books)
                    # 适当休息，防止被封
                    time.sleep(2)
            
            st.success("所有批量任务已完成！")