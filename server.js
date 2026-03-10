const express = require("express");
const app = express();

app.use(express.json());
app.use(express.static("public"));

const STYLE_BRIEF = `
You are a writing coach who knows Mat's voice intimately. Mat is the co-founder/CEO of Leatherback Travel (Patch Adventures). 

HIS VOICE IN BRIEF:
- Tone: Like a message from a genuinely likeable, knowledgeable Australian mate. Warm but not gushing. Direct. Self-deprecating. Lightly irreverent.
- Radical transparency: admits mistakes plainly, shares real reasons behind decisions, doesn't bury bad news in corporate language
- Short paragraphs (1–3 sentences, often 1). Single-sentence standalone moments are his signature.
- Australian colour: "chuck a wobbly", "have a gander", "Wowee", "not bad!" — used naturally, not forced
- Humour: one well-placed, specific, observational joke. Subverts expectations. Light emoji use (one, max).
- Sentence patterns: starts with "And" or "But" freely; uses rhetorical questions he immediately answers; sets up assumptions then knocks them down; parenthetical asides for honesty/humour
- Openings: direct address, quick self-introduction, gets to the point fast. No "I hope this email finds you well."
- Closings: short, warm, personal. "That's it!" / "Cheers, Mat" / "We love you all"
- Subheadings: conversational, often a question, punchy — never dry or clinical

WHAT TO AVOID:
- Marketing buzzwords: "innovative", "passionate", "world-class", "synergy"
- Corporate hedging: "we would like to inform you that..."
- Long flowing paragraphs with formal sentence structures
- Excessive exclamation marks or emoji
- Clichéd travel writing: "immerse yourself in local culture"
- Vague hype: "exciting things ahead!"

YOUR TASK:
Analyse the submitted content against Mat's style. Return ONLY valid JSON in this exact format:
{
  "score": <number 1-10>,
  "verdict": "<one punchy sentence overall verdict>",
  "strengths": ["<specific thing done well>", "<another>"],
  "issues": [{"quote": "<exact excerpt from text, max 12 words>", "issue": "<what's wrong>", "fix": "<suggested rewrite>"}]
}
Be specific. Quote directly from the submitted text in issues. Always include as many issues as you can find — aim for 4-6 even on good content. There is always something to improve.
`;

app.post("/api/check", async (req, res) => {
  const { text } = req.body;
  if (!text || !text.trim()) {
    return res.status(400).json({ error: "No text provided" });
  }

  try {
    const response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": process.env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 1500,
        system: STYLE_BRIEF,
        messages: [{ role: "user", content: `Check this content against Mat's style:\n\n${text}` }],
      }),
    });

    const data = await response.json();
    const raw = data.content.map((b) => b.text || "").join("");
    const clean = raw.replace(/```json|```/g, "").trim();
    const result = JSON.parse(clean);
    res.json(result);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: "Something went wrong. Try again." });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Running on port ${PORT}`));
