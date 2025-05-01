from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

model_path = "finetuned_phi3"

# Загрузка модели и токенизатора
tokenizer = AutoTokenizer.from_pretrained(model_path)
tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained(model_path)

while True:
    prompt = input("\nВаш вопрос (или 'выход'): ")
    if prompt.lower() in ['выход', 'exit']:
        break

    inputs = tokenizer(prompt, return_tensors="pt", padding=True)
    input_ids = inputs["input_ids"]

    with torch.no_grad():
        output = model.generate(input_ids, max_new_tokens=50)

    print("\nОтвет модели:")
    print(tokenizer.decode(output[0], skip_special_tokens=True))
