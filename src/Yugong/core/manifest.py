import json
import os

from src.Yugong.core.logger import BotLogger


class Manifest:
    """
    S/L Manifest Json
    """
    def __init__(self, file):
        self.logger = BotLogger("manifest")
        self.file = file
        self.data = {}
        self.data = self.load()

    def load(self) -> dict[str, any]:
        """
        加载 history.json 文件，如果不存在则创建空结构

        Returns:
            dict: 历史数据结构 {'tea': {topic: []}}
        """
        try:
            with open(self.file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.logger.info(f"已加载 history.json 文件")
                self.data = data
                return data
        except FileNotFoundError:
            # 文件不存在，创建空结构
            data = {}
            self.save(data=data)
            self.logger.info(f"已创建新的 history.json 文件")
            self.data = data
            return data
        except json.JSONDecodeError as e:
            data = {}
            self.save(data=data)
            self.logger.info(f"警告：history.json 格式错误 - {e}，将使用空结构")
            self.data = data
            return {}

    def save(self, data: dict[str, any] = None):
        """
        保存数据到 history.json 文件

        Args:
            data: 要保存的数据，如果为 None 则保存当前 self.history
        """
        if data is None:
            data = getattr(self, 'data', {})

        os.makedirs(os.path.dirname(self.file), exist_ok=True)

        try:
            with open(self.file, 'w', encoding='utf-8') as f:
                # noinspection PyTypeChecker
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"已保存到 history.json")

            if data is not self.data:
                self.data = data
        except Exception as e:
            self.logger.error(f"保存 history.json 失败 - {e}")