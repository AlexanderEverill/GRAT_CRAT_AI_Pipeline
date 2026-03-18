from openai import OpenAI
import hashlib
import json
import datetime

client = OpenAI()

def call_llm(system_prompt, user_prompt):
    response = client.responses.create(
        model="gpt-5",
        temperature=0,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    output_text = response.output_text

    audit_record = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "model": "gpt-5",
        "system_prompt_hash": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "user_prompt_hash": hashlib.sha256(user_prompt.encode()).hexdigest()
    }

    return output_text, audit_record
