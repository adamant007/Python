# Direct YouTube automation

The repository is prepared to upload rendered Shorts directly to YouTube without
Metricool, Buffer, or a paid browser automation service.

## One-time private credentials

Create a Google Cloud OAuth client that has access to the YouTube Data API v3,
authorize the Ginger Dragon Studios YouTube account with the
`https://www.googleapis.com/auth/youtube.upload` scope, and store these three
values as **GitHub Actions repository secrets**:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Do not commit those values to the repository.

Once all three secrets exist, every new `videos/*.mp4` render automatically
runs `.github/workflows/publish-youtube.yml`.

## Google audit restriction

Google currently restricts videos uploaded with `videos.insert` from
unverified API projects created after July 28, 2020 to private viewing mode.
The workflow still uploads them and requests scheduled publication, but the
Google Cloud project must pass YouTube's API compliance audit before unattended
public publishing can be relied on.

Official reference:
https://developers.google.com/youtube/v3/docs/videos/insert
