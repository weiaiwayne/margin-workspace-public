# Launch post drafts

## LinkedIn

We’ve been building heavily with AI agents on cloud servers. One thing kept coming up: we needed a better way to review their work.

An agent writes a plan, an audit, or technical documentation in Markdown. We read it, question a paragraph, suggest a change, and send it back—much as we would with a human author. But doing that across terminal sessions and files gets awkward, especially when colleagues also want to weigh in.

So we built **Margin Workspace**.

It brings familiar document editing and comments into a folder-based workspace on your own server. Think Google Docs for the review experience and Dropbox for organizing the work, while keeping the documents as ordinary Markdown and text files.

You can highlight a passage, leave comments, edit the document, and invite collaborators. When you’re ready, Margin exports the comments alongside the file and generates a prompt you can give to your coding agent for the next revision.

Today we’re open-sourcing it through LampBotics AI Lab.

To get started, copy the setup prompt in the README into your CLI coding agent on a supported VPS. The agent can install Margin, configure HTTPS, and help you connect your project folders. You’ll need a domain and server access; no AI API subscription is required to run Margin itself.

It’s still a small-team tool, not a complete replacement for Google Docs or Dropbox. In particular, it doesn’t yet support simultaneous co-editing. But it makes the cycle of human review and agent revision much easier to follow.

Repository and setup prompt:
https://github.com/weiaiwayne/margin-workspace-public

You can also ask your CLI coding agent to fix bugs or add features, then contribute the changes through a fork and pull request. We welcome agent-assisted contributions.

I’d love to hear how others are reviewing agents’ plans and work—and what would make that process better.

## X — single post

AI agents write plans in Markdown. Humans need to review them.

We built Margin: document editing and comments in a shared folder workspace on your VPS.

Now open source. Give the README’s setup prompt to your CLI agent:
https://github.com/weiaiwayne/margin-workspace-public

## Optional follow-up reply

Highlight a passage, comment, edit, and export feedback for the next agent revision. Files stay on your server. Setup needs a domain and a supported Linux VPS. No simultaneous co-editing yet; this is a practical tool for small teams working with AI agents.

## Contribution reply

Want a feature or found a bug? Ask your CLI coding agent to improve Margin, test the change, and open a pull request from your fork. Agent-assisted contributions are welcome. The contribution guide includes a prompt for that too.
