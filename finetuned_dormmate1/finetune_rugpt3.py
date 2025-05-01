from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments, TextDataset, DataCollatorForLanguageModeling

model_name = "sberbank-ai/rugpt3small_based_on_gpt2"
tokenizer = AutoTokenizer.from_pretrained(model_name)
tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained(model_name)

def load_dataset(file_path, tokenizer):
    return TextDataset(
        tokenizer=tokenizer,
        file_path=file_path,
        block_size=128
    )

train_dataset = load_dataset("dataset.txt", tokenizer)
data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

training_args = TrainingArguments(
    output_dir="../finetuned_dormmate",
    overwrite_output_dir=True,
    num_train_epochs=15,
    per_device_train_batch_size=1,
    save_steps=50,
    save_total_limit=1,
    logging_steps=10,
    prediction_loss_only=True
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    data_collator=data_collator
)

print("⏳ Дообучение началось...")
trainer.train()
print("✅ Дообучение завершено!")

model.save_pretrained("./finetuned_dormmate1")
tokenizer.save_pretrained("./finetuned_dormmate1")
