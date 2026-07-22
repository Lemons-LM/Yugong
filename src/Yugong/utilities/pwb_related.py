import os

from pywikibot import family


class QiuwenFamily(family.Family):
    """Qiuwen family."""

    name = "qiuwen"
    langs = {"zh": os.environ.get("QIUWEN_DOMAIN", "www.qiuwenbaike.cn")}

    def scriptpath(self, code):
        return ""

    def protocol(self, code):
        return "HTTPS"

    def isPublic(self):
        return False


family.Family._families["qiuwen"] = QiuwenFamily()