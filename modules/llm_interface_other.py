# modules/llm_interface.py

import requests
import os
from groq import Groq
import transformers
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline, BitsAndBytesConfig

import torch.distributed as dist

LOADED_MODELS = {}

def generate_llm_response(model_name, combined_prompt, params):
    """
    A generic function that calls the appropriate LLM provider.
    combined_prompt now can include:
       - 'system_prompt': str
       - 'conversation': list of { role: 'user'|'assistant', content: str }
    """
    if "huggingface" in model_name.lower():
        return call_huggingface_transformers(combined_prompt, params)



def get_loaded_model(model_path, model_name, params):
    if model_name in LOADED_MODELS:
        return LOADED_MODELS[model_name]
    
    # Create an appropriate BitsAndBytesConfig to avoid deprecated parameters
    if model_name == "llama-3.3-70b-instruct-bnb-4bit-unsloth":
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            quantization_config=quantization_config,
            device_map="auto"
        )
    else:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16  # Ensure dtype consistency with input type.
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            quantization_config=quantization_config,
            device_map="auto",
            attn_implementation="flash_attention_2"
        )

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    # Create the text generation pipeline
    text_generation_pipeline = pipeline(
        task="text-generation",
        model=model,
        tokenizer=tokenizer,
    )

    LOADED_MODELS[model_name] = text_generation_pipeline
    return text_generation_pipeline

def model_name_map(model_name):
    mapping = {
        "groq-llm": "llama-3.3-70b-versatile",
        "huggingface_llama3.1_70b_4bit": "llama-3.3-70b-instruct-bnb-4bit-unsloth",
        "huggingface_phi-4": "phi-4"
    }
    return mapping.get(model_name.lower(), "llama-3.3-70b-versatile")

model_name = "phi-4"
model_path = f"/scratch/maxspad_root/maxspad0/jspagnol/hf_models/{model_name}"

quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16  # Ensure dtype consistency with input type.
        )
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    quantization_config=quantization_config,
    device_map="auto",
    attn_implementation="flash_attention_2"
)

tokenizer = AutoTokenizer.from_pretrained(model_path)

def call_huggingface_transformers(combined_prompt, params):
    # Map the model name and create the model path
    model_name = model_name_map(params.get("model_name", "llama-3.3-70b-instruct-bnb-4bit-unsloth"))
    model_path = f"/scratch/maxspad_root/maxspad0/jspagnol/hf_models/{model_name}"
    
    # Get cached pipeline (loads from disk only the first time)
    text_generation_pipeline = get_loaded_model(model_path, model_name, params)

    # Prepare prompts from combined_prompt
    system_prompt = combined_prompt.get('system_prompt', '').strip()
    conversation = combined_prompt.get('conversation', [])
    user_prompt = combined_prompt.get('user_prompt', '').strip()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    for msg in conversation:
        messages.append({"role": msg['role'], "content": msg['content']})

    if user_prompt:
        messages.append({"role": "user", "content": user_prompt})

    # Generate the response
    outputs = text_generation_pipeline(
        messages,
        temperature=params.get("temperature", 0.0),
        max_new_tokens=params.get("max_tokens", 8000),
        top_p=params.get("top_p", 1.0)
    )
    print(outputs)

    # Depending on your pipeline output structure, adjust extraction of the response.
    response = outputs[0]["generated_text"][-1]["content"]
    return {
        "content": response
    }


