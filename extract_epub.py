#!/usr/bin/env python3
"""
EPUB Content Extractor
提取 EPUB 内容并转换为 Markdown 格式
"""

import os
import re
from bs4 import BeautifulSoup
from pathlib import Path

class EPUBExtractor:
    def __init__(self, epub_dir):
        self.epub_dir = Path(epub_dir)
        self.text_dir = self.epub_dir / "text"
        self.output_dir = Path("translated_content")
        self.output_dir.mkdir(exist_ok=True)

    def clean_html(self, html_content):
        """清理 HTML 并提取纯文本"""
        soup = BeautifulSoup(html_content, 'html.parser')

        # 移除script和style标签
        for script in soup(["script", "style"]):
            script.decompose()

        return soup

    def html_to_markdown(self, soup):
        """将 HTML 转换为 Markdown"""
        markdown_parts = []

        # 处理标题
        for i in range(1, 7):
            for heading in soup.find_all(f'h{i}'):
                text = heading.get_text().strip()
                markdown_parts.append(f"{'#' * i} {text}\n\n")

        # 处理段落
        for para in soup.find_all('p'):
            text = para.get_text().strip()
            if text:
                # 处理斜体
                text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', str(para))
                text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text)
                # 处理粗体
                text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text)
                text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text)
                # 清理 HTML 标签
                text = BeautifulSoup(text, 'html.parser').get_text()
                markdown_parts.append(f"{text}\n\n")

        # 处理引用
        for blockquote in soup.find_all('blockquote'):
            text = blockquote.get_text().strip()
            lines = text.split('\n')
            for line in lines:
                if line.strip():
                    markdown_parts.append(f"> {line.strip()}\n")
            markdown_parts.append("\n")

        return ''.join(markdown_parts)

    def extract_chapter(self, file_path):
        """提取单个章节内容"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        soup = self.clean_html(content)

        # 提取标题
        title_tag = soup.find('title')
        title = title_tag.get_text() if title_tag else "Untitled"

        # 提取正文
        body = soup.find('body')
        if not body:
            return None, None

        # 转换为 Markdown
        markdown = self.html_to_markdown(body)

        return title, markdown

    def extract_all_chapters(self):
        """提取所有章节"""
        # 定义章节顺序（根据 toc.ncx）
        chapter_files = [
            ("part0006.html", "Start Here", "从这里开始"),
            # Section I
            ("part0007_split_000.html", "Section I: How We Got Here", "第一部分：我们如何走到这一步"),
            ("part0008_split_001.html", "Chapter 1: How We Got Here", "第1章：我们如何走到这一步"),
            ("part0009_split_001.html", "Chapter 2: Grand Slam Offers", "第2章：大满贯报价"),
            # Section II
            ("part0010_split_000.html", "Section II: Pricing", "第二部分：定价"),
            ("part0011_split_001.html", "Chapter 3: The Commodity Problem", "第3章：商品化陷阱"),
            ("part0012_split_001.html", "Chapter 4: Finding The Right Market", "第4章：寻找正确的市场"),
            ("part0013_split_001.html", "Chapter 5: Charge What It's Worth", "第5章：收取价值相符的价格"),
            # Section III
            ("part0014_split_000.html", "Section III: Value", "第三部分：价值"),
            ("part0015_split_001.html", "Chapter 6: The Value Equation", "第6章：价值方程式"),
            ("part0016_split_001.html", "Chapter 7: Free Goodwill", "第7章：免费的善意"),
            ("part0017_split_001.html", "Chapter 8: The Thought Process", "第8章：思维过程"),
            ("part0018_split_001.html", "Chapter 9: Problems & Solutions", "第9章：问题与解决方案"),
            ("part0019_split_001.html", "Chapter 10: Trim & Stack", "第10章：精简与堆叠"),
            # Section IV
            ("part0020_split_000.html", "Section IV: Enhancing Your Offer", "第四部分：增强你的报价"),
            ("part0021_split_001.html", "Chapter 11: Overview", "第11章：概述"),
            ("part0022_split_001.html", "Chapter 12: Scarcity", "第12章：稀缺性"),
            ("part0023_split_001.html", "Chapter 13: Urgency", "第13章：紧迫性"),
            ("part0024_split_001.html", "Chapter 14: Bonuses", "第14章：赠品"),
            ("part0025_split_001.html", "Chapter 15: Guarantees", "第15章：保证"),
            ("part0026_split_001.html", "Chapter 16: Naming", "第16章：命名"),
            # Section V
            ("part0027_split_000.html", "Section V: Execution", "第五部分：执行"),
            ("part0028.html", "Your First $100,000", "你的第一个10万美元"),
        ]

        extracted = []

        for file_name, en_title, ch_title in chapter_files:
            file_path = self.text_dir / file_name
            if file_path.exists():
                print(f"Extracting: {file_name}")
                title, content = self.extract_chapter(file_path)
                if content:
                    extracted.append({
                        'file': file_name,
                        'en_title': en_title,
                        'ch_title': ch_title,
                        'content': content
                    })

                    # 保存为单独的 Markdown 文件
                    safe_filename = re.sub(r'[^\w\s-]', '', ch_title).strip().replace(' ', '_')
                    output_file = self.output_dir / f"{safe_filename}_original.md"

                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(f"# {en_title}\n")
                        f.write(f"## {ch_title}\n\n")
                        f.write("---\n\n")
                        f.write(content)

                    print(f"  Saved to: {output_file}")
            else:
                print(f"  File not found: {file_path}")

        return extracted

def main():
    extractor = EPUBExtractor("epub_extracted")
    chapters = extractor.extract_all_chapters()
    print(f"\n提取完成！共提取 {len(chapters)} 个章节")
    print(f"输出目录: {extractor.output_dir}")

if __name__ == "__main__":
    main()
