GOLDMAN MILL: OUTSIDE RSS FEEDS -> MILL MESSENGER MASTODON
===========================================================
Free GitHub Actions starter: no dlvr.it slot or MastoFeed required.

THE IMPORTANT DISTINCTION
This publishes stories arriving from OUTSIDE RSS/Atom feeds selected by you,
not your own WordPress posts. Your existing WordPress-to-Mastodon connection is
unaffected. Nothing happens until you set up your repository and token.

THE NEW FEATURES (different for EACH outside RSS feed)
- hashtags: list of hashtags to add to that feed's posts
- include_any: only publish if title OR RSS summary contains one of these phrases
- exclude_any: never publish when title OR RSS summary contains one of these phrases
- attach_image: false by default. If true, attempt to attach an image provided
  directly by the RSS feed. No image in feed, or upload fails? Post title/link only.
  Only enable this if you have permission to republish the images. Automatic
  Mastodon link previews may already display an image without direct attachment.

FIRST STEP: Create your FREE GitHub repository
1. Go to https://github.com/ and sign in (create a free account if needed).
2. Use the + menu, choose New repository.
3. Name it: goldman-mill-rss
4. Select PUBLIC. Do not add a license or .gitignore yet; README is optional.
5. Click Create repository.

SECOND STEP (AFTER THE REPOSITORY EXISTS): Upload the files
1. Unzip the downloaded starter kit on your computer.
2. Open settings.json with Notepad. Set mastodon_server to the server part of
   your Mastodon account's address (for example https://mastodon.social).
3. For each feed, give a name and replace the RSS URL sample. Add objects for
   additional feed sources, separated with commas. Keep all quotes and commas.
   Please DO NOT paste your Mastodon password or access token into any file.
4. IMPORTANT: leave posting_enabled as false for the first test.
5. In GitHub repository, select Add file > Upload files. Upload the CONTENTS of
   the unzipped folder, not the ZIP itself. The .github folder can be hidden in
   Windows; if browser upload does not preserve .github/workflows, create a file
   in GitHub with the EXACT name:
          .github/workflows/rss-to-mastodon.yml
   and paste the contents of the kit's identically named file.
6. Check in GitHub's file listing that the workflow appears under .github.

THIRD STEP: Secure authorization
1. At your Mastodon account: Preferences / Settings > Development > New
   application. Grant write:statuses. If you intend to attach feed images,
   also grant write:media. The account owner must create this app.
2. Copy its USER access token. Never share it in chat or a public repository.
3. In your GitHub repository: Settings > Secrets and variables > Actions >
   New repository secret. Name EXACTLY: MASTODON_ACCESS_TOKEN
   Paste the token as the secret value. Save.
4. In GitHub Settings > Actions > General, make sure workflows have permission
   to write repository contents, since the bot saves posted_state.json.

FOURTH STEP: Test safely, then activate
1. Repository > Actions > Goldman Mill - Curated RSS to Mastodon > Run workflow.
2. The first successful check creates posted_state.json and says it posted ZERO
   old entries. That's expected. The initial sample feed must have been edited.
3. Check that the state file appeared in the repository.
4. Edit settings.json: change ONLY posting_enabled from false to true.
5. New incoming RSS entries will post as TITLE + LINK + that feed's HASHTAGS.
   A configured filter must match. Optional RSS-supplied images require
   Mastodon write:media permission and republishing rights.
6. When MastoFeed resumes, turn off its identical feed so that the same news
   does not reach Mastodon twice.

CONFIG EXAMPLE (replace with YOUR actual URLs)
{
 "mastodon_server": "https://mastodon.social",
 "posting_enabled": false,
 "check_limit": 20,
 "feeds": [
   {
     "name": "Peace news",
     "url": "https://example.org/feed",
     "hashtags": ["#Peace", "#Nonviolence"],
     "include_any": [],
     "exclude_any": ["sports betting"],
     "attach_image": false
   },
   {
     "name": "Climate news",
     "url": "https://climate.example.org/rss",
     "hashtags": ["#ClimateJustice"],
     "include_any": ["climate", "environment"],
     "exclude_any": [],
     "attach_image": false
   }
 ]
}

NOTES
- GitHub schedule checks about every 30 minutes, but jobs can start late.
- 20 posts/run is a SAFETY CAP, not a monthly subscription quota. Adjust to 1-40.
- A newly added feed starts silently and NEVER dumps its old items at once.
- Manual and scheduled runs use the same history file to reduce duplicates.
- If your public repository goes 60 days without activity, GitHub may disable
  its scheduled workflow. Check the Actions tab occasionally.
- PUBLIC repository means the RSS source list is publicly visible. Secret
  Mastodon access tokens stay under GitHub Secrets, NEVER in the files.
- If your news feed offers only very short RSS entries or no image URLs, images
  will not be uploaded. The original linked site may still unfurl a preview.

REFERENCE DOCUMENTATION
GitHub upload: https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository
GitHub schedule: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
Mastodon statuses: https://docs.joinmastodon.org/methods/statuses/
Mastodon media: https://docs.joinmastodon.org/methods/media/
