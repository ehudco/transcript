from firestore_client import get_job
job = get_job('68821899-9ff3-44e3-9d2b-710e3f85a977')
tok = job.get('oauth_tokens') or {}
print('has tokens:', bool(tok))
print('scopes:', tok.get('scopes'))
print('has refresh_token:', bool(tok.get('refresh_token')))
print('client_id present:', bool(tok.get('client_id')))
print('client_secret present:', bool(tok.get('client_secret')))
print('token_uri:', tok.get('token_uri'))
