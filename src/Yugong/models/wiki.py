import json
import os
import re
import sys


from pathlib import Path

import pywikibot

from pywikibot import config
from pywikibot.comms import http

from src.wikibot.core.logger import BotLogger
from src.wikibot.core.mailer import mailer
from src.wikibot.utilities.link import get_user_talk
from src.wikibot.utilities.path_helper import PROJECT_ROOT

class Wiki:
    def __init__(self, bot_name: str, api_endpoint: str = "https://www.qiuwenbaike.cn/api.php"):
        if not bot_name.strip() or not api_endpoint.strip():
            raise ValueError("Bot name and api endpoint cannot be empty")
        self.bot_name = bot_name
        self._site = None
        self.api_endpoint = api_endpoint
        self.logger = BotLogger("wiki")
        self.csrf_token = ""
        self.logger.info("已初始化 WikiBot")
        Path(os.path.join(PROJECT_ROOT, "data","bot")).mkdir(parents=True, exist_ok=True)
        self.heartbeat_file = os.path.join(PROJECT_ROOT, "data","bot", "heartbeat")
        self.heartbeat = ""
        self.request_count = 20
        self._tick_disabled = False
        self.tick()

    def get_sections(self, title: str, *, level: str="2") -> list[str]:
        """
        获取页面的所有二级标题 (== ... ==)

        Args:
            title: 页面标题

        Returns:
            list: 二级标题名称列表
            :param title:
            :param level:
        """
        self.tick()
        level = str(level)
        params = {
            "action": "parse",
            "page": title,
            "prop": "sections",
            "format": "json"
        }

        response = http.session.get(self.api_endpoint, params=params)
        if not response:
            return []

        data = response.json()

        if "error" in data:
            return []

        sections = data.get("parse", {}).get("sections", [])

        # 筛选二级标题 (level == "2")
        level_sections = []
        if not sections:
            return []
        for section in sections:
            if section.get("level") == level:
                level_sections.append(section.get("linkAnchor", "").strip())

        return level_sections

    def get_message_list(self, *, page: str) -> list[str]:
        text = self.page(page).text
        json_list = json.loads(text).get("targets", [])
        result = []
        for json_item in json_list:
            result.append(json_item.get("title", ""))
        return result

    def new_section(self, title: str, section_title: str, content: str, summary: str) -> None:
        page = self.page(title)
        try:
            old_text = page.text
            new_text = old_text.strip() + "\n\n== " + section_title + " ==\n" + content
            page.text = new_text
            page.save(
                summary=summary,
                bot=True
            )
        except Exception as e:
            self.logger.error(f"发布失败：{e}")

    def mass_message(self, mass_message_list: str, title: str, content: str, summary: str) -> None:
        message_list = self.get_message_list(page=mass_message_list)
        self.logger.info(f"正在发布MassMessage到：{mass_message_list}\n标题：{title}\n内容：{content}\n摘要：{summary}")
        for target in message_list:
            try:
                if not self.check_allow_bots(target):
                    self.logger.info(f"该用户不允许机器人发送通知")
                    continue
                self.logger.info(f"\n正在发布到：{target}")
                self.new_section(title=target, section_title=title, content=content, summary=summary)
            except Exception as e:
                self.logger.exception(e)
                continue

    def check_allow_bots(self, user: str) -> bool:
        """
        检查用户是否允许机器人操作
        """
        text: str = get_user_talk(user)
        if not text:
            return False
        if re.search(r'\{\{(nobots|bots\|(allow=none|deny=.*?' + self.bot_name + r'.*?|optout=all|deny=all))\}\}', text):
            return False
        return True

    def _check_suppressed_action(self) -> None:
        """
        检查用户是否禁止机器人操作
        """
        self._tick_disabled = True
        try:
            params = {
                "action": "query",
                "titles": "User:" + self.bot_name + "/block",
                "prop": "revisions",
                "rvprop": "ids",
                "format": "json"
            }
            response = http.session.get(self.api_endpoint, params=params)
            if not response:
                return
            data = response.json()["query"]["pages"]
            page_data= next(iter(data.values()))
            if "revisions" in page_data:
                revid = page_data["revisions"][0]["revid"]
                if not os.path.exists(self.heartbeat_file):
                    with open(self.heartbeat_file, 'w', encoding='utf-8') as f:
                        f.write(str(revid))
                        self.heartbeat = str(revid)
                        return
                else:
                    with open(self.heartbeat_file, 'r', encoding='utf-8') as f:
                        heartbeat_in_file = f.read()
                if heartbeat_in_file and not self.heartbeat:
                    self.heartbeat = str(heartbeat_in_file)
                if str(self.heartbeat) != str(revid):
                    self.logger.critical("机器人被禁止操作")
                    mailer.email("机器人被禁止操作", "机器人被禁止操作，请及时处理！")
                    sys.exit(1)
        finally:
            self._tick_disabled = False

    @property
    def site(self) -> pywikibot.Site:
        """获取 Pywikibot Site（懒初始化）"""
        if self._site is None:
            oauth_token = os.environ.get("MW_BOT_OAUTH_TOKEN")
            if not oauth_token:
                raise ValueError("未找到 MW_BOT_OAUTH_TOKEN 环境变量")
            config.user_agent_format = 'Qiuwen/1.1 {username}/{script} ({script_comments}) {pwb}' '{python} {http_backend}'
            config.cosmetic_changes = True
            config.datafilepath(os.path.join(PROJECT_ROOT, "data", "pwb"))
            config.minthrottle = 2


            self._site = pywikibot.Site(
                code="zh",
                fam="qiuwen",
                user=self.bot_name,
            )

            self.logger.info("已初始化 Pywikibot Site")

        self.tick()
        return self._site

    def page(self, title):
        return pywikibot.Page(self.site, title)

    def category(self, title):
        return pywikibot.Category(self.site, title)

    def user(self, name):
        return pywikibot.User(self.site, name)

    def file(self, title):
        return pywikibot.FilePage(self.site, title)

    def tick(self):
        if self._tick_disabled:          # 若被禁用则直接返回
            return
        self.request_count += 1
        if self.request_count >= 20:
            self._check_suppressed_action()
            self.request_count = 0

wiki = Wiki(bot_name="Lemonade-bot")

_original_request = http.session.request

OAUTH_TOKEN = os.environ.get("MW_BOT_OAUTH_TOKEN")

def guarded_request(method, url, *args, **kwargs):
    # 这里拿不到 self，所以需要全局 wiki 实例
    wiki.tick()
    print(f"Wiki request: {method} {url} {kwargs}")
    headers = kwargs.get('headers', {})
    if OAUTH_TOKEN and 'Authorization' not in headers:
        headers['Authorization'] = f'Bearer {OAUTH_TOKEN}'
        kwargs['headers'] = headers

    return _original_request(method, url, *args, **kwargs)


http.session.request = guarded_request