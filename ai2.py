from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# ============================================================
# CONFIG
# ============================================================

DATABASE_FILE = Path("database.json")

BOT_NAME = "Lupey"

EXIT_COMMANDS = {"quit", "exit", "bye"}

FUZZY_MATCH_THRESHOLD = 0.72
MAX_HISTORY = 20

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# ============================================================
# DATA
# ============================================================

@dataclass
class QuestionEntry:
    question: str
    answers: list[str]
    created_at: float
    times_asked: int = 0
    source: str = "user"

# ============================================================
# BOT
# ============================================================

class SmartChatBot:

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database = self._load_database()
        self.history: list[tuple[str, str]] = []

    # ========================================================
    # DATABASE
    # ========================================================

    def _load_database(self) -> dict[str, Any]:
        if not self.database_path.exists() or self.database_path.stat().st_size == 0:
            return {"questions": []}
        try:
            with self.database_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("questions", [])
            return data
        except Exception as e:
            logging.error(f"DB load error: {e}")
            return {"questions": []}

    def _save_database(self):
        try:
            with self.database_path.open("w", encoding="utf-8") as f:
                json.dump(self.database, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"DB save error: {e}")

    # ========================================================
    # TEXT UTILS
    # ========================================================

    @staticmethod
    def normalize_text(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    # ========================================================
    # INTENT CLASSIFIER
    # ========================================================

    def classify_intent(self, user_input: str) -> str:
        text = self.normalize_text(user_input)

        chat_phrases = [
            "hi", "hello", "hey",
            "how are you", "whats up",
            "who are you", "what is your name",
            "thanks", "bye"
        ]
        if any(p in text for p in chat_phrases):
            return "chat"

        if text.startswith(("what ", "why ", "how ", "when ", "where ", "who ")):
            return "web"

        return "memory"

    # ========================================================
    # CHAT RESPONSES
    # ========================================================

    def chat_response(self, user_input: str) -> str:
        text = self.normalize_text(user_input)

        chat_map = {
            "hi": ["Hi!", "Hello!", "Hey!"],
            "hello": ["Hello!", "Hey there!"],
            "hey": ["Hey!", "Hi!"],
            "how are you": ["I'm good, thanks!", "All well here.", "Doing fine!"],
            "whats up": ["Not much, just learning.", "All good!"],
            "who are you": [f"I'm {BOT_NAME}, your chatbot."],
            "what is your name": [f"My name is {BOT_NAME}."],
            "thanks": ["You're welcome!", "No problem!"],
            "bye": ["Goodbye!", "See you later!"]
        }

        for k, v in chat_map.items():
            if self.similarity(text, k) > 0.8:
                return random.choice(v)

        return "I'm not sure yet."

    # ========================================================
    # MEMORY MATCHING
    # ========================================================

    def find_best_match(self, user_input: str):
        norm = self.normalize_text(user_input)
        best, best_score = None, 0
        for entry in self.database["questions"]:
            q = self.normalize_text(entry["question"])
            score = self.similarity(norm, q) + len(set(norm.split()) & set(q.split())) * 0.05
            if score > best_score:
                best, best_score = entry, score
        return best if best_score >= FUZZY_MATCH_THRESHOLD else None

    # ========================================================
    # LEARNING
    # ========================================================

    def learn(self, q: str, a: str, source="user"):
        q, a = self.normalize_text(q), a.strip()
        if len(a) < 3:
            return
        for entry in self.database["questions"]:
            if self.normalize_text(entry["question"]) == q:
                if any(a.lower() == x.lower() for x in entry["answers"]):
                    return
                entry["answers"].append(a)
                entry["source"] = source
                self._save_database()
                return
        self.database["questions"].append(asdict(QuestionEntry(
            question=q,
            answers=[a],
            created_at=time.time(),
            source=source
        )))
        self._save_database()

    # ========================================================
    # WEB SEARCH + SMART FILTER
    # ========================================================

    def search_web(self, query: str) -> str | None:
        try:
            r = requests.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            soup = BeautifulSoup(r.text, "html.parser")
            results = soup.select(".result__snippet")

            for item in results:
                text = re.sub(r"\s+", " ", item.get_text(strip=True))
                # skip definitions, translations, long stories
                bad_keywords = ("definition:", "dictionary", "pronunciation", "translation", "learn more")
                if any(b in text.lower() for b in bad_keywords):
                    continue
                # skip very long snippets (>25 words)
                if len(text.split()) > 25:
                    continue
                # skip snippets that are questions
                if text.endswith("?"):
                    continue
                # prioritize short human-like sentences
                if 5 <= len(text.split()) <= 25:
                    return text
            return None
        except Exception as e:
            logging.error(f"Web error: {e}")
            return None

    # ========================================================
    # MEMORY HISTORY
    # ========================================================

    def remember(self, u, b):
        self.history.append((u, b))
        if len(self.history) > MAX_HISTORY:
            self.history.pop(0)

    # ========================================================
    # FALLBACK
    # ========================================================

    def memory_fallback(self):
        if not self.history:
            return random.choice(["Interesting.", "Tell me more.", "I'm still learning."])
        last_topic = self.history[-1][0]
        return f"Tell me more about '{last_topic}'."

    # ========================================================
    # MAIN BRAIN
    # ========================================================

    def generate_smart_response(self, user_input: str) -> str:
        intent = self.classify_intent(user_input)
        if intent == "chat":
            return self.chat_response(user_input)
        match = self.find_best_match(user_input)
        if match:
            return random.choice(match["answers"])
        web_result = self.search_web(user_input)
        if web_result:
            self.learn(user_input, web_result, "web")
            return web_result
        return self.memory_fallback()

    # ========================================================
    # RUN LOOP
    # ========================================================

    def run(self):
        print("=" * 50)
        print(f"{BOT_NAME} SELF-BUILDING BOT")
        print("=" * 50)
        while True:
            user = input("\nYou: ").strip()
            if not user:
                continue
            if user.lower() in EXIT_COMMANDS:
                print(f"{BOT_NAME}: Goodbye.")
                break
            response = self.generate_smart_response(user)
            print(f"\n{BOT_NAME}: {response}")
            self.remember(user, response)
            feedback = input("\nGood response? (y/n/skip): ").strip().lower()
            if feedback == "n":
                better = input("Teach better response: ").strip()
                if better:
                    self.learn(user, better, "user")
                    print("Learned!")

# ============================================================
# MAIN
# ============================================================

def main():
    SmartChatBot(DATABASE_FILE).run()

if __name__ == "__main__":
    main()