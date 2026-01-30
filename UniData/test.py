import secrets
import string

def generate_random_key(length=32):
    """生成指定长度的随机密钥"""
    # 定义可打印字符集
    characters = string.ascii_letters + string.digits  # 大小写字母 + 数字
    # 生成随机密钥
    random_key = ''.join(secrets.choice(characters) for _ in range(length))
    return random_key

# 生成 32 位随机密钥
key = generate_random_key(32)
print(f"随机密钥: {key}")
print(f"密钥长度: {len(key)}")
