import boto3
import json

print("Starting Bedrock test...")

client = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1"   # change if your region is different
)

prompt = "Give Facebook ad copy for a skincare product"

body = {
    "anthropic_version": "bedrock-2023-05-31",
    "messages": [
        {"role": "user", "content": prompt}
    ],
    "max_tokens": 200
}

print("Sending request to Bedrock...")

response = client.invoke_model(
    modelId="anthropic.claude-3-sonnet-20240229-v1:0",
    body=json.dumps(body)
)

print("Response received!")

result = json.loads(response["body"].read())

print("\n=== AI RESPONSE ===\n")
print(result["content"][0]["text"])