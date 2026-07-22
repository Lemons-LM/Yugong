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
        Load history.json file; create empty structure if it doesn't exist.

        Returns:
            dict: History data structure
        """
        try:
            with open(self.file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.logger.info("Loaded history.json")
                self.data = data
                return data
        except FileNotFoundError:
            # File doesn't exist — create empty structure
            data = {}
            self.save(data=data)
            self.logger.info("Created new history.json")
            self.data = data
            return data
        except json.JSONDecodeError as e:
            data = {}
            self.save(data=data)
            self.logger.warning(f"history.json format error - {e}, using empty structure")
            self.data = data
            return {}

    def save(self, data: dict[str, any] = None):
        """
        Save data to history.json.

        Args:
            data: Data to save; if None, saves current self.data
        """
        if data is None:
            data = getattr(self, 'data', {})

        os.makedirs(os.path.dirname(self.file), exist_ok=True)

        try:
            with open(self.file, 'w', encoding='utf-8') as f:
                # noinspection PyTypeChecker
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info("Saved to history.json")

            if data is not self.data:
                self.data = data
        except Exception as e:
            self.logger.error(f"Failed to save history.json - {e}")