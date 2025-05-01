from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

# Загружаем дообученную модель
model_path = "../finetuned_dormmate"
tokenizer = AutoTokenizer.from_pretrained(model_path)
tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained(model_path)

# Цикл общения
while True:
    prompt = input("\nВаш вопрос (или 'выход'): ").strip()
    if prompt.lower() in ['выход', 'exit']:
        break

    # Формируем формат, как в обучающем датасете
    formatted = f"Вопрос: {prompt} Ответ:"
    inputs = tokenizer(formatted, return_tensors="pt", padding=True)
    input_ids = inputs["input_ids"]
    attention_mask = inputs["attention_mask"]

    # Генерация ответа
    with torch.no_grad():
        output = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=100,
            do_sample=True,
            top_k=50,
            top_p=0.95,
            temperature=0.9,
            pad_token_id=tokenizer.eos_token_id
        )

    decoded = tokenizer.decode(output[0], skip_special_tokens=True)
    if "Ответ:" in decoded:
        print("\nОтвет модели:")
        print(decoded.split("Ответ:")[1].strip())
    else:
        print("\n⚠️ Не удалось извлечь ответ.")
