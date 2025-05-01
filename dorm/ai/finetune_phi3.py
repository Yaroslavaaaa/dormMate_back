from torch.utils.data import Dataset, DataLoader
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments
import os


# === Заглушка-датасет ===
class DummyDataset(Dataset):
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.samples = ["Привет, как дела?", "Как поступить в университет?", "Что такое AI?"]

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        inputs = self.tokenizer(self.samples[idx], return_tensors="pt", truncation=True, padding="max_length",
                                max_length=32)
        return {
            "input_ids": inputs.input_ids.squeeze(),
            "attention_mask": inputs.attention_mask.squeeze(),
            "labels": inputs.input_ids.squeeze()
        }


# === Подготовка ===
print("Загружаем токенизатор и модель (mini)...")
tokenizer = AutoTokenizer.from_pretrained("tiiuae/falcon-rw-1b")  # маленькая модель
model = AutoModelForCausalLM.from_pretrained("tiiuae/falcon-rw-1b")

dataset = DummyDataset(tokenizer)

train_loader = DataLoader(
    dataset,
    batch_size=1,
    num_workers=0,
    pin_memory=False
)

# === Параметры обучения ===
training_args = TrainingArguments(
    output_dir="./finetuned_phi3",
    per_device_train_batch_size=1,
    num_train_epochs=1,
    logging_dir="./logs",
    save_total_limit=1,
    logging_steps=1,
    save_steps=5,
    fp16=False,
    report_to=[]
)


# === Trainer (эмуляция обучения) ===
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    tokenizer=tokenizer
)

print("Начинаем безопасное CPU-обучение...")
trainer.train()
print("Обучение завершено!")
