import json
import random 
from difflib import get_close_matches

def load_database (file_path: str) -> dict:
    with open (file_path, 'r') as file:
        data: dict = json.load(file)
    return data

def update_database (file_path: str, data: dict):
    with open (file_path, 'w') as file:
        json.dump(data, file, indent=2)

def get_best_match (user_question: str, questions: list[str]) -> str | None:
    user_question = user_question.lower()
    lowercased_questions = [q.lower() for q in questions]
    
    matches: list = get_close_matches (user_question, lowercased_questions, n=1, cutoff=0.6)
    
    if matches:
        index = lowercased_questions.index(matches[0])
        return questions[index]
    return None

def get_answer (question: str, database: dict) -> str | None:
    for q in database["questions"]:
        if q["question"].lower() == question.lower():
            return random.choice(q["answers"])

def chat_bot():
    database: dict = load_database("database.json")

    while True:
        user_input: str = input("Lupey:")

        if user_input.lower() == "quit":
            break

        all_questions = [q["question"] for q in database["questions"]]
        best_match: str | None = get_best_match(user_input, all_questions)

        if best_match:
            answer: str = get_answer(best_match, database)
            print(f'Bot: {answer}')
        else:
            print("Bot: Please give me the answer so that I can learn and get stronger.")
            new_answer: str = input("The Answer or 'skip': ")

            if new_answer.lower() != "skip":
                database["questions"].append({"question": user_input.lower(), "answers": [new_answer]})
                update_database("database.json", database)
                print("Bot: I will remember that.")

if __name__ == '__main__':
    chat_bot()