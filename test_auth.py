import tweepy

client = tweepy.Client(
    bearer_token="dummy_bearer",
    consumer_key="dummy_ck",
    consumer_secret="dummy_cs",
    access_token="dummy_at",
    access_token_secret="dummy_ats"
)

print("Auth used:", client.session.auth)
