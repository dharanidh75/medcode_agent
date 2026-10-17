import os
import httpx
import json

SYSTEM_PROMPT = """You are an expert clinical text structuring assistant. Your sole purpose is to extract 
key clinical concepts from medical discharge summaries and format them as a strict 
JSON object for downstream ICD-10 code retrieval.

RULES:
1. DO NOT act as a diagnostician. Only extract what is explicitly stated in the text.
2. DO NOT paraphrase, normalize, or expand medical terms or abbreviations. Preserve 
   exact clinical terminology and abbreviations exactly as written in the source 
   (e.g. keep "HTN" as "HTN", not "hypertension"). Paraphrasing degrades retrieval 
   accuracy against the embedding index.
3. DO NOT include negated or ruled-out findings (e.g. "no signs of infection", 
   "pneumonia ruled out") in diagnoses, procedures, symptoms, or medications. 
   Place these instead in "negated_findings".
4. For each extracted item, include the exact verbatim full sentence from the 
   source text it was extracted from, as "source_span". It is CRITICAL that you provide 
   the entire surrounding sentence to preserve context, not just the isolated term. Do not summarize 
   or alter the span — copy the full sentence exactly as it appears in the input.
5. If a category has no relevant information in the source text, output an empty 
   array for it. Never guess or fabricate entries.
6. Output ONLY valid JSON in the exact format below. No markdown, no code fences, 
   no explanation, no additional text before or after the JSON.

OUTPUT FORMAT:
{
  "diagnoses": [{"term": "string", "source_span": "string"}],
  "procedures": [{"term": "string", "source_span": "string"}],
  "symptoms": [{"term": "string", "source_span": "string"}],
  "medications": [{"term": "string", "source_span": "string"}],
  "negated_findings": [{"term": "string", "source_span": "string"}]
}"""

async def structure_clinical_text(raw_text: str) -> dict:
    """
    Sends the raw clinical text to Groq and expects a JSON response containing
    structured clinical entities.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("Error: GROQ_API_KEY environment variable is not set")
        return {"diagnoses": [], "procedures": [], "symptoms": [], "medications": []}
        
    model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Structure the following discharge summary:\n\n{raw_text}"}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            response_content = data["choices"][0]["message"]["content"]
            return json.loads(response_content)
    except Exception as e:
        print(f"Error calling Groq API: {e}")
        # Return empty structured schema on failure so the pipeline doesn't break entirely
        return {
            "diagnoses": [],
            "procedures": [],
            "symptoms": [],
            "medications": []
        }
