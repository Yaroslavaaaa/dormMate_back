# dorm/ai_model.py

from pathlib import Path
import torch
from transformers import GPT2Tokenizer, GPT2LMHeadModel

# КОРЕНЬ проекта → dormMate_back
BASE_DIR  = Path(__file__).resolve().parents[1]
MODEL_DIR = BASE_DIR / "finetuned_dormmate"

# Локальная загрузка GPT-2 токенизатора и модели
tokenizer = GPT2Tokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
tokenizer.pad_token     = tokenizer.eos_token
tokenizer.pad_token_id  = tokenizer.eos_token_id
model     = GPT2LMHeadModel.from_pretrained(MODEL_DIR, local_files_only=True)

def generate_answer_from_model(prompt: str) -> str:
    """
    Генерирует ответ с помощью локальной дообученной GPT-2 модели.
    """
    formatted = f"Вопрос: {prompt.strip()} Ответ:"
    inputs    = tokenizer(formatted, return_tensors="pt", padding=True)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=100,
            do_sample=True,
            top_k=50,
            top_p=0.95,
            temperature=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )
    text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return text.split("Ответ:")[-1].strip()
