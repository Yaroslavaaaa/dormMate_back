from torch.utils.data import Dataset, DataLoader
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments


class DummyDataset(Dataset):
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.samples = ["Привет, как дела?", "Как подать заявку на общежитие?", "Что такое машинное обучение?"]

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        inputs = self.tokenizer(
            self.samples[idx],
            return_tensors="pt",
            truncation=True,
            padding="max_length",
            max_length=32
        )
        return {
            "input_ids": inputs.input_ids.squeeze(),
            "attention_mask": inputs.attention_mask.squeeze(),
            "labels": inputs.input_ids.squeeze()
        }


# Загружаем токенизатор и модель
print("Загружаем токенизатор и модель (tiny-gpt2)...")
tokenizer = AutoTokenizer.from_pretrained("sshleifer/tiny-gpt2")
tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained("sshleifer/tiny-gpt2")

# Подготовка датасета
dataset = DummyDataset(tokenizer)

# Параметры обучения
training_args = TrainingArguments(
    output_dir="finetuned_phi3",
    per_device_train_batch_size=1,
    num_train_epochs=1,
    logging_dir="./logs",
    save_total_limit=1,
    logging_steps=1,
    save_steps=5,
    fp16=False,
    report_to=[]
)

# Тренер
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    tokenizer=tokenizer
)

print("Начинаем безопасное CPU-обучение...")
trainer.train()
print("Обучение завершено!")

# Сохраняем токенизатор и модель
tokenizer.save_pretrained("./finetuned_phi3")
model.save_pretrained("./finetuned_phi3")
