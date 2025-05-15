from werkzeug.security import generate_password_hash,check_password_hash

# Sample plain passwords
passwords = ['balaaj123', 'wajdan123', 'baqir123']

# Generate and print hashed passwords
for i, pwd in enumerate(passwords, start=1):
    hashed = generate_password_hash(pwd)
    print(f"hashed_password{i} = '{hashed}'")
    print(check_password_hash(hashed, pwd))