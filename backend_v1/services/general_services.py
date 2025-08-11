import hashlib as hash

def calculate_content_hash(content: str, alg='sha256') -> str:
    encoded_content = content.encode()
    hasher = hash.new(alg)
    hasher.update(encoded_content)
    return hasher.hexdigest()