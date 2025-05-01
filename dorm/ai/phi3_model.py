from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# Загружаем Phi-3 модель
tokenizer = AutoTokenizer.from_pretrained("microsoft/phi-2")
model_phi3 = AutoModelForCausalLM.from_pretrained("microsoft/phi-2", torch_dtype=torch.float32)

def ask_phi3(question):
    prompt = f"Ответь кратко и понятно:\n{question}"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True)
    outputs = model_phi3.generate(**inputs, max_new_tokens=100)
    answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
    # убираем лишние пробелы и сам prompt из начала
    return answer.split("Ответь кратко и понятно:")[-1].strip()
