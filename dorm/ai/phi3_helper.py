from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

model_name = "microsoft/Phi-3-mini-4k-instruct"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    device_map="auto",
    trust_remote_code=True,
    offload_folder="offload",
)

generator = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=300,
    temperature=0.2,
)

def ask_phi3(question: str) -> str:
    prompt = f"Ответь кратко и понятно на вопрос студента:\n{question}\nОтвет:"
    outputs = generator(prompt, do_sample=True)
    text = outputs[0]['generated_text']
    if "Ответ:" in text:
        text = text.split("Ответ:")[-1].strip()
    return text[:1000].strip()
