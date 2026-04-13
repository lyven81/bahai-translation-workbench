# Bahai Chinese Translation Workbench

An AI-assisted translation pipeline for translating Baha'i Sacred Writings into Chinese. Built with reverence for the Word of God and respect for the translators who serve it.

## Try It Now

**Live demo:** [Launch the Workbench](https://bahai-translation-workbench-522143897885.asia-southeast1.run.app)

Log in with one of the demo accounts to explore:

| Role | Name | What you can do |
|------|------|-----------------|
| Coordinator | Zhang Wei | Create documents, assign governors, manage team |
| Governor | Li Ming | Review and approve translations |

## The Challenge We Face Today

The translation of Baha'i Sacred Writings into Chinese currently follows a 7-stage manual pipeline, producing approximately one publication per year across a 12-month cycle.

AI currently assists only at Stage 1 (initial draft). The remaining stages are entirely manual. Most translator time is spent on production work -- grammar checks, formatting, and consistency reviews -- leaving less time for the higher-value work that only humans can do: verifying meaning, judging theological accuracy, and refining spiritual tone.

This workbench was built to change that balance.

## Three Sacred Standards

Every translation produced by this workbench is held to three standards, drawn from the guidance of the Guardian and the Universal House of Justice:

**Accuracy (准确)**
Faithful to the original meaning. Nothing added, removed, or reinterpreted.

**Beauty (文风优美)**
Elevated, literary Chinese. Not colloquial. The language must carry the dignity of sacred scripture.

**Consistency (风格一致)**
Aligned with the style established by the Guardian. Formal, classical-influenced modern Chinese.

> "Translation is indeed a most difficult art -- an art in which absolute perfection is unattainable."
> -- From guidance on behalf of the Universal House of Justice

## How It Works: AI Produces, Humans Govern

The workbench follows one principle: **AI proposes, humans decide.**

- **AI handles production** -- drafting translations, checking grammar, validating formatting, and enforcing terminology consistency. The repetitive work that consumes translator time.
- **Humans focus on what matters** -- verifying theological meaning, judging spiritual tone, and ensuring the language carries the right weight.
- **No one is displaced.** The same translators remain. Their role shifts from doing the work to governing the work.
- **Two human checkpoints.** The pipeline does not advance without human approval.

## The Pipeline

The full pipeline has five stages. AI handles three; humans govern two.

```
Stage 1 ── Translation ──── AI
   AI generates a Chinese draft using the approved terminology glossary.

Stage 2 ── Review ────────── HUMAN
   The governor reviews for meaning accuracy and theological correctness.
   Decision: approve, edit, or reject.

Stage 3 ── Editing ───────── AI
   AI refines grammar, punctuation, tone, and terminology consistency.

Stage 4 ── Typesetting ───── AI
   AI validates formatting: punctuation marks, paragraph alignment, title markers.

Stage 5 ── Proofread ─────── HUMAN
   The governor compares the final output against the approved Stage 2 text.
```

## What's Available Today (Phase 1)

Phase 1 is live and ready to use. It covers the first three stages of the pipeline:

- **AI translates** the source text into Chinese using the approved glossary
- **You review** the translation side-by-side with the original text
- **You decide** -- approve it, edit it, or reject it
- **AI refines** the approved translation for grammar, tone, and consistency
- **AI self-checks** against the three sacred standards and reports results

No login required. Single user. Immediate use.

## What's Coming

### Phase 2: Team Workflow
- Name-based login for team members added by a coordinator
- Coordinator creates documents and assigns governors
- **Single Governor model** -- one person reviews at both Stage 2 and Stage 5 (shorter documents)
- **Dual Governor model** -- Governor A reviews at Stage 2, Governor B at Stage 5 (longer documents, fresh eyes)
- Governors in different locations and time zones work asynchronously

### Phase 3: Multi-Model Pipeline and Dashboard
- Coordinator selects which AI model to use at each stage
- Available models: Claude (Anthropic), GPT-4 (OpenAI), Gemini (Google), DeepSeek
- Different models have different strengths for Chinese literary prose
- Pipeline dashboard shows documents by stage, bottlenecks, and progress in real time

## Same Team, Elevated Roles

| Before | After |
|--------|-------|
| Translators doing manual translation, review, and editing | **Pipeline Governors** -- review and approve AI output |
| 1 publication pipeline | **Terminology Specialists** -- maintain the glossary |
| Each person produces work | **Pipeline Coordinators** -- assign documents and track progress |
| ~12 months per publication | **Final Reviewers** -- institutional approval |
| Limited time for theological reflection | 4-6 parallel pipelines running simultaneously |

Everyone is elevated to higher-value decision-making.

## Terminology Glossary

The workbench maintains a centralized glossary of approved Baha'i terms. The AI uses these terms automatically in every translation. Examples:

| English | Chinese | Category |
|---------|---------|----------|
| Baha'u'llah | 巴哈欧拉 | Person |
| Manifestation of God | 上帝的显圣者 | Theology |
| Universal House of Justice | 世界正义院 | Institution |
| The Kitab-i-Aqdas | 《亚格达斯经》 | Scripture |
| consultation | 磋商 | Concept |
| the Blessed Beauty | 天佑美尊 | Title |

The full glossary contains 21 terms across 5 categories: persons, institutions, theology, concepts, and scriptures.

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/lyven81/bahai-translation-workbench.git
   cd bahai-translation-workbench
   ```

2. Create a `.env` file with your API key:
   ```
   ANTHROPIC_API_KEY=your-key-here
   ```

3. Install dependencies and start:
   ```
   pip install -r requirements.txt
   uvicorn app:app --host 0.0.0.0 --port 8080
   ```

   Or on Windows, run `start.bat`.

4. Open `http://localhost:8080` in your browser.

## Links

- **Live demo:** [Launch the Workbench](https://bahai-translation-workbench-522143897885.asia-southeast1.run.app)
- **GitHub:** [github.com/lyven81/bahai-translation-workbench](https://github.com/lyven81/bahai-translation-workbench)
