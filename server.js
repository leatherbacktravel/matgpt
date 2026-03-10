// Leatherback Voice Check — server
// Requires: pandoc (for .docx), pdftotext/poppler-utils (for .pdf)
// Set ANTHROPIC_API_KEY env var before running
// To swap the logo: replace the SVG in public/index.html header, or
// place your logo.png in public/ and use <img src="/logo.png"> instead

const express = require("express");
const multer = require("multer");
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

const app = express();
app.use(express.json({ limit: "5mb" }));
app.use(express.static("public"));

const upload = multer({ dest: os.tmpdir(), limits: { fileSize: 10 * 1024 * 1024 } });

// ─── Writers Brief (system prompt) ──────────────────────────────────────────
const STYLE_BRIEF = `
You are a writing coach for Leatherback Travel. You know the brand voice intimately — it was built by Mat, co-founder/CEO, and is the standard all Leatherback content should meet.

THE LEATHERBACK VOICE:
- Tone: Like a message from a genuinely likeable, knowledgeable Australian mate. Warm but not gushing. Direct. Self-deprecating. Lightly irreverent.
- Radical transparency: admits mistakes plainly, shares real reasons behind decisions, doesn't bury bad news in corporate language
- Short paragraphs (1–3 sentences, often 1). Single-sentence standalone moments are the signature.
- Australian colour: "chuck a wobbly", "have a gander", "Wowee", "not bad!" — used naturally, not forced
- Humour: one well-placed, specific, observational joke. Subverts expectations. Light emoji use (one, max).
- Sentence patterns: starts with "And" or "But" freely; rhetorical questions answered immediately; sets up assumptions then knocks them down; parenthetical asides for honesty/humour
- Openings: direct address, quick self-introduction, gets to the point fast. No "I hope this email finds you well."
- Closings: short, warm, personal. "That's it!" / "Cheers, Mat" / "We love you all"
- Subheadings: conversational, often a question, punchy — never dry or clinical
- Formatting: very short paragraphs, bold for key data, ellipses for pauses, em dashes for pivots, parentheses for asides

WHAT TO AVOID:
- Marketing buzzwords: "innovative", "passionate", "world-class", "synergy"
- Corporate hedging: "we would like to inform you that..."
- Long flowing paragraphs with formal sentence structures
- Excessive exclamation marks or emoji
- Clichéd travel writing: "immerse yourself in local culture"
- Vague hype: "exciting things ahead!"
- Anything that sounds like it was written by a committee
- Over-apologising or being excessively deferential

YOUR TASK:
Analyse the submitted content against the Leatherback voice. Return ONLY valid JSON in this exact format:
{
  "categories": {
    "tone": {
      "grade": "<one of: Strong, Good, Developing, Off-brand>",
      "summary": "<1-2 sentences on how well the tone matches — warm, direct, mate-like quality>"
    },
    "structure": {
      "grade": "<one of: Strong, Good, Developing, Off-brand>",
      "summary": "<1-2 sentences on paragraph length, sentence rhythm, punchiness>"
    },
    "authenticity": {
      "grade": "<one of: Strong, Good, Developing, Off-brand>",
      "summary": "<1-2 sentences on transparency, honesty, real-talk vs corporate-speak>"
    },
    "language": {
      "grade": "<one of: Strong, Good, Developing, Off-brand>",
      "summary": "<1-2 sentences on word choice — buzzwords, jargon, natural Australian colour>"
    },
    "personality": {
      "grade": "<one of: Strong, Good, Developing, Off-brand>",
      "summary": "<1-2 sentences on humour, warmth, self-deprecation, human feel>"
    }
  },
  "feedback": [
    {
      "section": "<which part of the text this refers to — e.g. 'Opening paragraph', 'Subject line', 'Third paragraph'>",
      "quote": "<exact excerpt from text, 5-15 words>",
      "comment": "<detailed explanation of what's working or not working and WHY, 2-4 sentences>",
      "suggestion": "<specific rewrite or actionable advice, or null if the quote is good>"
    }
  ]
}

GRADING GUIDE:
- "Strong" = nails the Leatherback voice, reads like it came from the team
- "Good" = mostly there, minor tweaks needed
- "Developing" = has elements but needs meaningful work in this area
- "Off-brand" = doesn't reflect the Leatherback voice in this dimension

Be generous but honest. Good content should get "Good" or "Strong" grades. Reserve "Off-brand" for content that genuinely misses the mark.

For feedback: be thorough and constructive. Include BOTH praise and criticism. Aim for 5-8 feedback items. Quote directly from the text. Explain the reasoning — don't just say "too corporate", say WHY it feels corporate and what would fix it. Be specific and useful. This feedback will be delivered as a professional document, so write it to be genuinely helpful to the writer.
`;

// ─── Extract text from uploaded files ───────────────────────────────────────
function extractText(filePath, mimetype, originalname) {
  const ext = path.extname(originalname).toLowerCase();

  if (ext === ".docx") {
    try {
      const text = execSync(`pandoc "${filePath}" -t plain --wrap=none`, { encoding: "utf-8", timeout: 15000 });
      return text.trim();
    } catch (e) {
      throw new Error("Could not read the .docx file. Please try pasting the text instead.");
    }
  }

  if (ext === ".pdf") {
    try {
      const text = execSync(`pdftotext "${filePath}" -`, { encoding: "utf-8", timeout: 15000 });
      return text.trim();
    } catch (e) {
      throw new Error("Could not read the PDF. Please try pasting the text instead.");
    }
  }

  if (ext === ".txt" || ext === ".md") {
    return fs.readFileSync(filePath, "utf-8").trim();
  }

  throw new Error("Unsupported file type. Please upload a .docx, .pdf, or .txt file.");
}

// ─── Check endpoint ─────────────────────────────────────────────────────────
app.post("/api/check", upload.single("file"), async (req, res) => {
  let text = req.body.text;

  // If a file was uploaded, extract text from it
  if (req.file) {
    try {
      text = extractText(req.file.path, req.file.mimetype, req.file.originalname);
    } catch (e) {
      return res.status(400).json({ error: e.message });
    } finally {
      // Clean up temp file
      try { fs.unlinkSync(req.file.path); } catch (_) {}
    }
  }

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
        max_tokens: 3000,
        system: STYLE_BRIEF,
        messages: [{ role: "user", content: `Check this content against the Leatherback voice:\n\n${text}` }],
      }),
    });

    const data = await response.json();

    if (data.error) {
      console.error("API error:", data.error);
      return res.status(500).json({ error: "API error. Check your API key and try again." });
    }

    const raw = data.content.map((b) => b.text || "").join("");
    const clean = raw.replace(/```json|```/g, "").trim();
    const result = JSON.parse(clean);

    // Include the original text for docx generation
    result._originalText = text;

    res.json(result);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: "Something went wrong. Try again." });
  }
});

// ─── Generate feedback docx ─────────────────────────────────────────────────
app.post("/api/export-docx", express.json({ limit: "5mb" }), async (req, res) => {
  const { categories, feedback, originalText } = req.body;

  if (!categories || !feedback) {
    return res.status(400).json({ error: "Missing feedback data" });
  }

  try {
    const {
      Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
      AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
      Header, Footer, PageNumber, LevelFormat
    } = require("docx");

    const gradeColor = (g) => {
      if (g === "Strong") return "1B8A6B";
      if (g === "Good") return "2E86AB";
      if (g === "Developing") return "D4940A";
      return "C44536";
    };

    const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
    const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };
    const thinBorder = { style: BorderStyle.SINGLE, size: 1, color: "E0E0E0" };
    const thinBorders = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };

    // Category grade table rows
    const catNames = {
      tone: "Tone & Warmth",
      structure: "Structure & Rhythm",
      authenticity: "Authenticity & Transparency",
      language: "Language & Word Choice",
      personality: "Personality & Humour"
    };

    const gradeRows = Object.entries(categories).map(([key, val]) => {
      return new TableRow({
        children: [
          new TableCell({
            borders: thinBorders,
            width: { size: 2800, type: WidthType.DXA },
            margins: { top: 80, bottom: 80, left: 120, right: 120 },
            children: [new Paragraph({ children: [new TextRun({ text: catNames[key] || key, bold: true, font: "Arial", size: 20 })] })]
          }),
          new TableCell({
            borders: thinBorders,
            width: { size: 1400, type: WidthType.DXA },
            margins: { top: 80, bottom: 80, left: 120, right: 120 },
            shading: { fill: gradeColor(val.grade), type: ShadingType.CLEAR },
            children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: val.grade, bold: true, font: "Arial", size: 20, color: "FFFFFF" })] })]
          }),
          new TableCell({
            borders: thinBorders,
            width: { size: 5160, type: WidthType.DXA },
            margins: { top: 80, bottom: 80, left: 120, right: 120 },
            children: [new Paragraph({ children: [new TextRun({ text: val.summary, font: "Arial", size: 20, color: "444444" })] })]
          }),
        ]
      });
    });

    // Feedback items
    const feedbackChildren = [];
    feedback.forEach((item, i) => {
      feedbackChildren.push(
        new Paragraph({
          spacing: { before: 240, after: 80 },
          children: [
            new TextRun({ text: `${i + 1}. ${item.section}`, bold: true, font: "Arial", size: 22 }),
          ]
        }),
        new Paragraph({
          spacing: { after: 80 },
          indent: { left: 360 },
          children: [
            new TextRun({ text: `"${item.quote}"`, italics: true, font: "Arial", size: 20, color: "666666" }),
          ]
        }),
        new Paragraph({
          spacing: { after: 80 },
          indent: { left: 360 },
          children: [
            new TextRun({ text: item.comment, font: "Arial", size: 20, color: "333333" }),
          ]
        })
      );
      if (item.suggestion) {
        feedbackChildren.push(
          new Paragraph({
            spacing: { after: 160 },
            indent: { left: 360 },
            children: [
              new TextRun({ text: "Suggestion: ", bold: true, font: "Arial", size: 20, color: "1B8A6B" }),
              new TextRun({ text: item.suggestion, font: "Arial", size: 20, color: "1B8A6B" }),
            ]
          })
        );
      }
    });

    const doc = new Document({
      styles: {
        default: { document: { run: { font: "Arial", size: 22 } } },
        paragraphStyles: [
          { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
            run: { size: 36, bold: true, font: "Arial", color: "1A1A1A" },
            paragraph: { spacing: { before: 0, after: 200 }, outlineLevel: 0 } },
          { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
            run: { size: 26, bold: true, font: "Arial", color: "333333" },
            paragraph: { spacing: { before: 300, after: 160 }, outlineLevel: 1 } },
        ]
      },
      sections: [{
        properties: {
          page: {
            size: { width: 12240, height: 15840 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
          }
        },
        headers: {
          default: new Header({
            children: [new Paragraph({
              children: [
                new TextRun({ text: "Leatherback Travel", font: "Arial", size: 16, color: "999999", bold: true }),
                new TextRun({ text: "  |  Voice Check Feedback", font: "Arial", size: 16, color: "BBBBBB" }),
              ]
            })]
          })
        },
        footers: {
          default: new Footer({
            children: [new Paragraph({
              alignment: AlignmentType.RIGHT,
              children: [
                new TextRun({ text: "Page ", font: "Arial", size: 16, color: "999999" }),
                new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "999999" }),
              ]
            })]
          })
        },
        children: [
          // Title
          new Paragraph({
            heading: HeadingLevel.HEADING_1,
            children: [new TextRun({ text: "Voice Check Report", bold: true, font: "Arial", size: 36 })]
          }),
          new Paragraph({
            spacing: { after: 80 },
            children: [new TextRun({ text: `Generated ${new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}`, font: "Arial", size: 20, color: "888888" })]
          }),
          // Divider
          new Paragraph({
            spacing: { after: 300 },
            border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "00A99A", space: 1 } },
            children: []
          }),

          // Category grades
          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            children: [new TextRun({ text: "Category Grades" })]
          }),
          new Table({
            width: { size: 9360, type: WidthType.DXA },
            columnWidths: [2800, 1400, 5160],
            rows: [
              new TableRow({
                children: [
                  new TableCell({
                    borders: thinBorders,
                    width: { size: 2800, type: WidthType.DXA },
                    margins: { top: 80, bottom: 80, left: 120, right: 120 },
                    shading: { fill: "F5F5F5", type: ShadingType.CLEAR },
                    children: [new Paragraph({ children: [new TextRun({ text: "Category", bold: true, font: "Arial", size: 20, color: "666666" })] })]
                  }),
                  new TableCell({
                    borders: thinBorders,
                    width: { size: 1400, type: WidthType.DXA },
                    margins: { top: 80, bottom: 80, left: 120, right: 120 },
                    shading: { fill: "F5F5F5", type: ShadingType.CLEAR },
                    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Grade", bold: true, font: "Arial", size: 20, color: "666666" })] })]
                  }),
                  new TableCell({
                    borders: thinBorders,
                    width: { size: 5160, type: WidthType.DXA },
                    margins: { top: 80, bottom: 80, left: 120, right: 120 },
                    shading: { fill: "F5F5F5", type: ShadingType.CLEAR },
                    children: [new Paragraph({ children: [new TextRun({ text: "Notes", bold: true, font: "Arial", size: 20, color: "666666" })] })]
                  }),
                ]
              }),
              ...gradeRows
            ]
          }),

          // Detailed feedback
          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            spacing: { before: 400 },
            children: [new TextRun({ text: "Detailed Feedback" })]
          }),
          new Paragraph({
            spacing: { after: 200 },
            children: [new TextRun({ text: "Each item below references a specific part of your text with commentary and suggestions.", font: "Arial", size: 20, color: "888888" })]
          }),
          ...feedbackChildren,

          // Original text section
          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            spacing: { before: 400 },
            children: [new TextRun({ text: "Original Text Reviewed" })]
          }),
          new Paragraph({
            spacing: { after: 200 },
            border: { left: { style: BorderStyle.SINGLE, size: 12, color: "E0E0E0", space: 8 } },
            indent: { left: 240 },
            children: [new TextRun({ text: originalText || "(not available)", font: "Arial", size: 20, color: "666666", italics: true })]
          }),
        ]
      }]
    });

    const buffer = await Packer.toBuffer(doc);

    res.setHeader("Content-Disposition", 'attachment; filename="voice-check-feedback.docx"');
    res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
    res.send(buffer);
  } catch (e) {
    console.error("Docx generation error:", e);
    res.status(500).json({ error: "Could not generate the feedback document." });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Running on port ${PORT}`));
