from src.Yugong.core.mailer import mailer
from collections import defaultdict


class Reporter:
    def __init__(self):
        self.issues = defaultdict(list)

    def add(self, module: str, issue: str):
        self.issues[module].append(issue)

    def report(self):
        if self.issues:
            subject = "Wikibot Report"
            body = "Wikibot Report\n\n"
            for module, issues in self.issues.items():
                body += f"{module}:\n"
                for issue in issues:
                    body += f"- {issue}\n"
            mailer.email(subject, body)

    def print(self):
        for module, issues in self.issues.items():
            print(f"{module}:")
            for issue in issues:
                print(f"- {issue}")

reporter: Reporter = Reporter()