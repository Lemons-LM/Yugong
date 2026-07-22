from pywikibot import family

from src.Yugong.core.settings import settings


class QiuwenFamily(family.Family):
    """Qiuwen family."""

    name = "qiuwen"
    langs = {"zh": getattr(settings, 'wiki_domain', 'www.qiuwenbaike.cn')}

    def scriptpath(self, code):
        return ""

    def protocol(self, code):
        return "HTTPS"

    def isPublic(self):
        return False


family.Family._families["qiuwen"] = QiuwenFamily()