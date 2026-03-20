# SQEG 2025 YMYL Knowledge Extraction

Source document: Search Quality Evaluator Guidelines, September 11, 2025

This file collects YMYL-relevant material from the guideline in chunk-friendly Markdown. Each chunk is self-contained and preserves the original section and PDF page references.

# Definitions and Harm Model

## [YMYL-001] High-Stakes Search Context
Category: Definitions and Harm Model
Section: 0.0 The Search Experience
Pages: p.5
YMYL relevance: The introduction frames why YMYL standards exist at all: some searches happen at critical moments and therefore require results that are authoritative, trustworthy, and not misleading.
Normalized note: The guideline introduces search as a system that must serve both casual and high-stakes needs. It explicitly contrasts entertainment queries with medical emergencies, which is the conceptual setup for YMYL. This matters for vector retrieval because later YMYL rules are not isolated exceptions; they are an extension of the document's core claim that search quality must scale with the risk of harm. When a query affects health, finances, safety, or public welfare, the result set is expected to be materially more reliable than for low-risk browsing.
Supporting excerpt: "critical moment of a person's life"
Citation: [SQEG 2025, sec. 0.0, p. 5]

## [YMYL-002] Why A Topic Becomes YMYL
Category: Definitions and Harm Model
Section: 2.3 Your Money or Your Life (YMYL) Topics
Pages: p.10
YMYL relevance: This is the core definition chunk. It explains the two main ways a topic becomes YMYL: direct danger from the topic itself, or significant harm if inaccurate or untrustworthy content is consumed.
Normalized note: The 2025 guideline ties YMYL to significant effects on health, financial stability, safety, or society. It then separates two causal paths. First, some topics are inherently dangerous, such as self-harm or violent extremism. Second, some topics become dangerous when the information is wrong, incomplete, or from a weak source. This second path is especially important for retrieval because it pulls in many ordinary-looking informational pages, such as voting or licensing guidance, that are only YMYL because accuracy and trustworthiness change real-world outcomes.
Supporting excerpt: "The topic itself is harmful" and "not accurate and trustworthy"
Citation: [SQEG 2025, sec. 2.3, p. 10]

## [YMYL-003] The Four 2025 YMYL Groupings
Category: YMYL Topic Types
Section: 2.3 Your Money or Your Life (YMYL) Topics
Pages: p.10
YMYL relevance: This chunk captures the 2025 categorical structure of YMYL, including the updated formulation of Government, Civics & Society.
Normalized note: The guideline organizes YMYL into four umbrella groups: Health or Safety, Financial Security, Government, Civics & Society, and Other. The third category is especially important in the September 2025 version because it explicitly includes public-interest issues, trust in institutions, and election or voting information. For knowledge-base purposes, this means YMYL is not limited to medicine and money. Content about public institutions, civic process, and society-wide informational issues should be indexed as YMYL when it can materially affect people's lives or the well-being of society.
Supporting excerpt: "Government, Civics & Society"
Citation: [SQEG 2025, sec. 2.3, p. 10]

## [YMYL-004] Boundary Heuristics And High Standards For Clear YMYL
Category: YMYL Topic Types
Section: 2.3 Your Money or Your Life (YMYL) Topics
Pages: pp.11-12
YMYL relevance: This chunk explains how to tell borderline topics apart and confirms that clear YMYL pages are held to unusually high Page Quality standards.
Normalized note: The guideline uses comparative examples to separate low-risk discussion from genuine YMYL risk. Weather or music-award chatter is generally not YMYL because slight inaccuracies are unlikely to cause significant harm. By contrast, advice on when to go to the emergency room, prescription drug purchasing, or hate-inciting opinion about a racial group can clearly produce serious harm. The document also gives a practical heuristic: if most people would be comfortable casually consulting friends, the topic is likely not YMYL. Once a page is on a clear YMYL topic, the rating standard rises sharply because low-quality content can negatively affect health, finances, safety, or society.
Supporting excerpt: "very high Page Quality rating standards"
Citation: [SQEG 2025, sec. 2.3, pp. 11-12]

# Experience vs Expertise

## [YMYL-005] Reputation Evidence For YMYL Is Expert-Led
Category: Trust, Reputation, and Accountability
Section: 3.3.1 Reputation of the Website; 3.3.5 What to Do When You Find No Reputation Information
Pages: pp.21, 24
YMYL relevance: YMYL reputation is not judged by generic popularity signals. The guideline says expert opinion carries special weight and missing reputation data requires closer scrutiny.
Normalized note: The guideline tells raters to rely on independent sources when assessing reputation and then tightens the rule for YMYL. For YMYL topics, the reputation of a site should be judged by what experts in the field say, not by self-description or simple popularity. Recommendations from professional societies or recognized experts are strong positive evidence. The document also warns that when reputation information is sparse, raters should pay more attention to other Page Quality signals, especially on YMYL pages. In practice, this means weak third-party reputation cannot be hand-waved away on high-risk topics.
Supporting excerpt: "judged by what experts in the field have to say"
Citation: [SQEG 2025, sec. 3.3.1 and 3.3.5, pp. 21, 24]

## [YMYL-006] Trust Is The Core E-E-A-T Signal
Category: Trust, Reputation, and Accountability
Section: 3.4 Experience, Expertise, Authoritativeness, and Trust (E-E-A-T)
Pages: pp.25-26
YMYL relevance: This chunk defines the general E-E-A-T framework in the way that matters most for YMYL: trust dominates the rest of the assessment.
Normalized note: The 2025 guideline states that Trust is the central member of the E-E-A-T family. Experience, expertise, and authority matter, but they do not rescue an untrustworthy page. This is crucial for YMYL evaluation because a page can look polished, technically expert, or socially authoritative and still fail if it is deceptive, unsafe, or unreliable. The guideline also notes that trust has dimensions beyond the acronym, such as customer service details for online stores or peer-reviewed support for academic claims. For retrieval, this chunk should be treated as a general rule that propagates through finance, medical, shopping, and civic YMYL pages.
Supporting excerpt: "The most important member ... is Trust"
Citation: [SQEG 2025, sec. 3.4, pp. 25-26]

## [YMYL-007] When Experience Is Enough And When Expertise Is Required
Category: Experience vs Expertise
Section: 3.4.1 YMYL Topics: Experience or Expertise?
Pages: p.27
YMYL relevance: This is the main rule for handling first-hand experience on YMYL topics without overgeneralizing formal expertise requirements.
Normalized note: The guideline allows two different trust models for YMYL. If a YMYL page is giving information or advice, a high level of expertise may be required. But if the page is sharing first-hand life experience around difficult situations, experience can support high E-E-A-T as long as the content remains trustworthy, safe, and aligned with well-established expert consensus. This is a major retrieval distinction: lived-experience content is not automatically low quality on YMYL topics, but it is only acceptable inside a bounded role. It can offer comfort, inspiration, or practical perspective, yet it cannot replace authoritative advice where expert knowledge is necessary.
Supporting excerpt: "some types of YMYL information and advice must come from experts"
Citation: [SQEG 2025, sec. 3.4.1, p. 27]

## [YMYL-008] Concrete 3.4.1 Examples: Cancer, Taxes, Retirement, Voting
Category: Experience vs Expertise
Section: 3.4.1 YMYL Topics: Experience or Expertise?
Pages: p.27
YMYL relevance: The example table operationalizes the experience-versus-expertise rule with concrete YMYL cases.
Normalized note: The examples show the split very clearly. For liver cancer, a page about coping with treatment can benefit from first-hand experience, but treatment options and life expectancy belong to expert guidance. For taxes, a humorous account of doing taxes is acceptable as experience, while instructions for filling out tax forms require expertise. For retirement, user reviews of retirement services can add value, but investment advice belongs to experts. For voting, a citizen's personal reason for voting can be useful experience, while eligibility and registration information must be accurate and authoritative. These examples should be indexed as decision rules, not just illustrations.
Supporting excerpt: "Information about who is eligible to vote"
Citation: [SQEG 2025, sec. 3.4.1, p. 27]

# Lowest/Low Signals for YMYL

## [YMYL-009] Early Lowest Screening For High-Trust YMYL Pages
Category: Lowest/Low Signals for YMYL
Section: 4.0 Lowest Quality Pages
Pages: pp.28-29
YMYL relevance: The guideline says raters should front-load harm screening before normal Page Quality scoring, and it names the high-trust page types that deserve special scrutiny.
Normalized note: The Lowest assessment is a screening stage, not just the end of a scoring continuum. Raters are instructed to first assess the true purpose of the page and then the page's potential to cause harm before moving to ordinary Page Quality considerations. The document explicitly says to give special scrutiny to pages or websites needing a high level of trust, such as online stores, medical websites, or news coverage of major civic issues. For YMYL retrieval, this means harm review is part of the entry criteria. High-stakes pages are evaluated through a stricter pre-check for deception, danger, and lack of trustworthiness.
Supporting excerpt: "Give special scrutiny"
Citation: [SQEG 2025, sec. 4.0, pp. 28-29]

## [YMYL-010] Harmfully Misleading Information On YMYL Topics
Category: Lowest/Low Signals for YMYL
Section: 4.4 Harmfully Misleading Information
Pages: p.33
YMYL relevance: This chunk captures the content patterns that make misinformation especially dangerous on YMYL topics.
Normalized note: The guideline treats misinformation as harmful when it can change consequential decisions or damage public welfare. The examples cover false claims about world leaders, false election dates, medical misinformation that contradicts expert consensus, and financial claims such as the idea that lottery tickets are a guaranteed retirement strategy. The section also includes unsubstantiated theories and claims not grounded in reasonable evidence. For YMYL indexing, this is a central rule cluster: the problem is not merely "low quality information" but information that can cause people to act wrongly in medicine, finances, civic participation, or institutional trust.
Supporting excerpt: "False dates for an election"
Citation: [SQEG 2025, sec. 4.4, p. 33]

## [YMYL-011] Missing Accountability, Sensitive Data, And High Inexpertise Trigger Lowest
Category: Lowest/Low Signals for YMYL
Section: 4.5 Untrustworthy Webpages or Websites; 4.5.1; 4.5.2
Pages: pp.34-35
YMYL relevance: This is one of the strictest YMYL rules in the document. It ties trust failure directly to missing accountability, sensitive-data handling, and lack of expertise.
Normalized note: The guideline says pages requiring a high level of trust must clearly identify who is responsible and how users can get help. Any site that handles personal, private, or sensitive data must provide extensive contact information. The YMYL-specific tightening is explicit: YMYL pages or sites handling sensitive data with no information about the website or content creator should be rated Lowest. The same section also says that if a page on YMYL topics is highly inexpert, it should be treated as untrustworthy and rated Lowest. This is a key retrieval rule because it links content quality, accountability, and transactional risk into a single YMYL failure pattern.
Supporting excerpt: "should be rated Lowest"
Citation: [SQEG 2025, sec. 4.5.1-4.5.2, pp. 34-35]

## [YMYL-012] Canonical Lowest YMYL Examples
Category: YMYL Examples and Edge Cases
Section: 4.7 Examples of Lowest Quality Pages
Pages: pp.45-48
YMYL relevance: These examples show how the abstract YMYL rules are applied to harmful civic, medical, and financial pages in practice.
Normalized note: The Lowest examples include multiple YMYL failure types. A hateful page targeting a specified group is YMYL because it harms both targeted people and society. A page asking for Social Security numbers, bank account data, and ATM PINs is YMYL because it weaponizes sensitive information. A debt-relief page is Lowest because it mixes deceptive design, scam indicators, and poor financial expertise. A fake cancer-cure page is Lowest because it contradicts scientific and medical consensus. A dry-socket medical page with no ownership or author information is Lowest because medical pages require high user trust. These examples are useful anchor cases for retrieval because they map the rules to concrete page types.
Supporting excerpt: "Medical pages require a high level of user trust"
Citation: [SQEG 2025, sec. 4.7, pp. 45-48]

## [YMYL-013] Low Quality YMYL Can Still Fail Without Reaching Lowest
Category: Lowest/Low Signals for YMYL
Section: 5.0 Low Quality Pages; 5.5 Unsatisfying Amount of Information about the Website or Content Creator
Pages: pp.58, 62-64
YMYL relevance: This chunk captures the middle band of YMYL failure, where pages are not overtly malicious but still fall below the standard because trust, effort, or expertise are insufficient.
Normalized note: The guideline says any topic can qualify for Low, but YMYL standards change the level of scrutiny. Pages needing a high level of trust deserve special attention, and transaction-oriented or YMYL pages can receive Low when there is too little customer service information, too little contact information, or too little clarity about responsibility. The examples show this in action. A health article about ginger is Low because it lacks accuracy and alignment with expert consensus. An adoption article is Low because it offers generic, low-effort, non-expert guidance on a consequential family decision. This chunk is important because not all YMYL problems are scams; some are simply too weak to be trusted.
Supporting excerpt: "should receive a Low rating"
Citation: [SQEG 2025, sec. 5.0 and 5.5, pp. 58, 62-64]

# High/Highest Signals for YMYL

## [YMYL-014] High And Highest Require Stronger Trust Signals On YMYL
Category: High/Highest Signals for YMYL
Section: 7.3 High Level of E-E-A-T; 8.2 Very Positive Reputation; 8.3 Very High Level of E-E-A-T
Pages: pp.72, 77
YMYL relevance: This chunk defines what strong YMYL quality looks like at the upper end of the scale.
Normalized note: For High quality, the guideline says trust is especially important on pages that process financial transactions or cover YMYL topics. For Highest quality, YMYL reputation is often grounded in recommendations from known experts or professional societies, rather than informal popularity signals. The document also says that very high E-E-A-T belongs to sources that are uniquely authoritative or go-to references for the topic. For vector retrieval, this chunk represents the positive mirror image of the Lowest rules: credible experts, strong institutional reputation, and uniquely authoritative status are the clearest markers that a YMYL page can support the top ratings.
Supporting excerpt: "Trust is especially important"
Citation: [SQEG 2025, sec. 7.3, 8.2, and 8.3, pp. 72, 77]

## [YMYL-015] Highest YMYL Examples Across News, Finance, Medical, Banking, And Charity
Category: YMYL Examples and Edge Cases
Section: 8.4 Examples of Highest Quality Pages
Pages: pp.78, 80-82
YMYL relevance: These are the clearest positive examples of YMYL pages meeting the strongest standard in the guideline.
Normalized note: The examples show several different routes to Highest on YMYL topics. Investigative reporting on environmental toxicity qualifies because it can affect health, financial security, businesses, and government agencies, and it is supported by award-level journalism. Financial examples include an official credit-report source and a federal tax-forms page, both justified by uniquely authoritative status. Medical examples include NIH-linked and highly reputable medical sources for BMI, meningitis, flu, and hospital treatment information. The banking login example shows that secure access to financial data is itself YMYL. The charity example shows that public-crisis and disaster-relief content can also be YMYL when the organization is highly reputable.
Supporting excerpt: "This is a YMYL topic"
Citation: [SQEG 2025, sec. 8.4, pp. 78, 80-82]

# YMYL Examples and Edge Cases

## [YMYL-016] Highly Meets And Needs Met Standards Tighten For YMYL
Category: YMYL Examples and Edge Cases
Section: 13.3 Highly Meets (HM); 14.0 The Relationship between Page Quality and Needs Met
Pages: pp.122, 141-142
YMYL relevance: YMYL affects not only Page Quality but also whether a result can count as highly helpful for the query.
Normalized note: The guideline says Highly Meets informational results on YMYL topics must be accurate and trustworthy, and medical or scientific results must reflect well-established consensus unless the user clearly wants an alternative viewpoint. It also warns that HM is not appropriate for untrustworthy, outdated, inaccurate, or otherwise undesirable pages. The dehydration example then shows the rule in action: a topical result is still unhelpful when its medical information is untrustworthy, while a highly authoritative medical source with reliable content is very helpful. This chunk matters for retrieval because it connects YMYL trust directly to usefulness, not just to standalone page quality.
Supporting excerpt: "must be accurate and trustworthy"
Citation: [SQEG 2025, sec. 13.3 and 14.0, pp. 122, 141-142]

## [YMYL-017] Civic And Public-Information Queries May Require Verification And Official Sources
Category: YMYL Examples and Edge Cases
Section: 22.1 Examples Where User Location Does (and Does Not) Matter
Pages: p.164
YMYL relevance: This query example demonstrates how civic or public-interest information becomes operationally YMYL at rating time.
Normalized note: The minimum-wage example is important because it combines public information, geographic specificity, and freshness verification. The guideline says the rater would need to verify that the answer shown is accurate for the user's state, and it treats official state and Department of Labor pages as the helpful sources. This is a useful retrieval case because it shows YMYL is not only about page authorship; it can also depend on whether the answer is current, locally correct, and institutionally sourced. Public-information queries that affect income, rights, or obligations can therefore carry YMYL-style accuracy requirements.
Supporting excerpt: "you would need to verify"
Citation: [SQEG 2025, sec. 22.1, p. 164]

## [YMYL-018] First-Hand Voting Experience Can Be Highest, But Inaccurate Voting Logistics Become Lowest
Category: YMYL Examples and Edge Cases
Section: 11.0 Page Quality Rating FAQs
Pages: p.91
YMYL relevance: This FAQ sharpens the 3.4.1 rule with a concrete civic example and makes the acceptable role of life experience very explicit.
Normalized note: The FAQ states that factual information and advice on YMYL topics should come from experts, while life experience can still produce Highest quality content if it is trustworthy, safe, and consistent with well-established expert consensus. The example is voting. A personal post about becoming a citizen and voting for the first time can be Highest quality as a life-experience page. But if that same page gives inaccurate information about when or where to vote, it should be rated Lowest because it could cause other people to miss their chance to vote. This chunk is especially valuable for retrieval because it cleanly separates acceptable narrative experience from unacceptable factual instruction on a civic YMYL topic.
Supporting excerpt: "rated Lowest because it could cause others to miss the opportunity to vote"
Citation: [SQEG 2025, sec. 11.0, p. 91]

# Version Notes

## [YMYL-019] September 2025 Update Flag
Category: Version Notes
Section: Appendix 2: Guideline Change Log
Pages: p.181
YMYL relevance: This chunk records that the 2025 document specifically updated YMYL definitions, which is important metadata for any downstream model or evaluator using this extraction.
Normalized note: The change log states that the September 2025 revision updated YMYL definitions and added extra examples for clarity. That means this extraction should be treated as grounded in the post-update YMYL framework, including the revised category wording and clarified example set. If this knowledge file is compared with older SQEG material, differences in YMYL scope should be assumed to be version-related unless proven otherwise. This chunk should remain attached to the collection so downstream systems know that the extraction reflects the September 11, 2025 guideline rather than an earlier edition.
Supporting excerpt: "Updated YMYL definitions"
Citation: [SQEG 2025, Appendix 2, p. 181]

---

# Casino-Specific YMYL Extracts

The following chunks apply the SQEG YMYL framework to online casino and gambling affiliate content. Each chunk is grounded in the same guideline sections as the general YMYL chunks above and uses the same citation format.

## [CASINO-001] Gambling As Financial Security YMYL
Category: YMYL Topic Types — Gambling / Financial Security
Section: 2.3 Your Money or Your Life (YMYL) Topics
Pages: p.10
YMYL relevance: Online gambling and casino content falls within the Financial Security YMYL category. Inaccurate claims about bonuses, winnings, withdrawal terms, or odds can cause users to make consequential financial decisions based on false information.
Normalized note: The guideline's Financial Security category covers any content that can significantly affect a person's financial stability. Gambling is a high-risk financial activity: users stake real money based on claims about payout rates, bonus values, withdrawal speeds, and platform licensing. An affiliate review that misrepresents any of these factors can cause real financial harm. This makes casino review content YMYL by the second causal path in sec. 2.3 — not because gambling is inherently dangerous in all contexts, but because inaccurate or incomplete information changes real-world financial outcomes for the reader. The high Page Quality standard that applies to financial advice therefore also applies to casino affiliate content when it makes factual claims about money, winnings, or terms.
Supporting excerpt: "significant effect on ... financial stability"
Citation: [SQEG 2025, sec. 2.3, p. 10]

## [CASINO-002] Misleading Bonus And Winnings Claims
Category: Lowest/Low Signals for YMYL — Financial Misinformation
Section: 4.4 Harmfully Misleading Information
Pages: p.33
YMYL relevance: Bonus and winnings claims that omit material terms or overstate expected returns are a direct parallel to the financial misinformation examples in sec. 4.4, such as "lottery tickets are a good retirement strategy."
Normalized note: Section 4.4 of the guideline identifies financial claims that are unsubstantiated or misleading as harmful misinformation. Casino affiliate content frequently presents bonus amounts, win rates, or payout speeds in ways that omit critical qualifying terms: wagering requirements, game restrictions, withdrawal caps, or time limits. Presenting a "200% bonus up to £500" without disclosing a 40x wagering requirement is structurally equivalent to a guaranteed-return financial claim. Similarly, stating that a casino "pays out within 24 hours" without noting that bank transfers take 3–5 business days is a misleading payment speed claim. Both patterns can cause users to commit real money based on a false picture of expected value. These violations map directly to the harmfully misleading information standard in sec. 4.4.
Supporting excerpt: "lottery tickets are a good retirement strategy"
Citation: [SQEG 2025, sec. 4.4, p. 33]

## [CASINO-003] Licensing And Regulatory Claims
Category: Lowest/Low Signals for YMYL — Trust and Accountability
Section: 4.5 Untrustworthy Webpages or Websites; 4.5.1; 4.5.2
Pages: pp.34-35
YMYL relevance: Licensing and regulatory status are safety-critical facts in gambling. Incorrect or unverified licensing claims fall under the accountability and high-inexpertise failure patterns in sec. 4.5.
Normalized note: The guideline says YMYL pages that are highly inexpert or that make accountability-related claims without supporting evidence should be rated Lowest. For casino affiliate content, licensing status is the primary trust signal users rely on to assess whether a platform is legal, regulated, and safe to deposit money with. A review that states a casino "holds a UKGC licence" without verification, or that fails to mention a licence has been suspended or revoked, introduces a material trust failure. The same applies to jurisdiction-specific claims: if a review asserts a casino accepts players from a country where it is not licenced to operate, this is both factually wrong and potentially harmful to the reader. These patterns match the accountability and high-inexpertise triggers in sec. 4.5.1 and 4.5.2.
Supporting excerpt: "should be rated Lowest"
Citation: [SQEG 2025, sec. 4.5.1-4.5.2, pp. 34-35]

## [CASINO-004] Responsible Gambling Omission As Trust Failure
Category: Lowest/Low Signals for YMYL — Health and Safety / Trust
Section: 3.4 Experience, Expertise, Authoritativeness, and Trust (E-E-A-T)
Pages: pp.25-26
YMYL relevance: Gambling content that promotes casino products without acknowledging addiction risk or responsible gambling resources fails the Trust dimension of E-E-A-T. This is a YMYL safety concern because gambling disorder is a recognized health condition with significant personal and financial consequences.
Normalized note: The guideline establishes Trust as the dominant E-E-A-T signal: a page that looks authoritative but is unsafe or unreliable fails the trust test regardless of other signals. In casino affiliate content, the trust dimension includes whether the review acknowledges the risks of gambling alongside its promotional content. Content that presents gambling exclusively as entertainment or a source of income, without any mention of addiction risk, self-exclusion tools, responsible gambling helplines, or the statistical reality of expected loss, is one-sided in a way that harms users who may be vulnerable. This is not a matter of personal opinion; it is a trust and safety standard grounded in the same E-E-A-T framework that applies to medical or financial advice. The omission pattern maps to the "unsafe or unreliable" failure mode in sec. 3.4.
Supporting excerpt: "The most important member ... is Trust"
Citation: [SQEG 2025, sec. 3.4, pp. 25-26]

## [CASINO-005] Affiliate Commercial Interest Must Not Distort Facts
Category: Experience vs Expertise — Affiliate Bias
Section: 3.4.1 YMYL Topics: Experience or Expertise?
Pages: p.27
YMYL relevance: Casino affiliate reviews operate under a commercial conflict of interest. The guideline's 3.4.1 framework implies that where YMYL information and advice is involved, the commercial interest of the author must not compromise the factual accuracy or completeness of the content.
Normalized note: Section 3.4.1 establishes that YMYL information and advice must meet the expertise standard appropriate to the topic. For casino affiliate content, this means that first-hand experience of a casino ("I played there and enjoyed it") is a legitimate perspective, but factual claims about bonuses, odds, licensing, withdrawal terms, or game fairness require accuracy regardless of the commercial relationship between the affiliate and the casino. An affiliate review that selectively omits negative findings, inflates ratings to favour commercial partners, or presents sponsored content as independent assessment distorts factual information in a way that violates the trust and expertise standard in 3.4.1. The key distinction: commercial tone and positive framing are acceptable, but factual distortion caused by undisclosed commercial interest is a YMYL trust failure.
Supporting excerpt: "some types of YMYL information and advice must come from experts"
Citation: [SQEG 2025, sec. 3.4.1, p. 27]

## [CASINO-006] Outdated Promotions And Regulatory Information
Category: Lowest/Low Signals for YMYL — Financial Misinformation / Accuracy
Section: 4.4 Harmfully Misleading Information
Pages: p.33
YMYL relevance: Casino promotions, bonus terms, withdrawal limits, and licensing status change frequently. Content that presents expired or superseded information as current is a form of misleading financial information under sec. 4.4.
Normalized note: The guideline's sec. 4.4 includes outdated or unsubstantiated financial claims as harmful misinformation. In casino affiliate content, temporal accuracy matters significantly: a welcome bonus that was available six months ago may have been withdrawn, halved, or had its terms materially worsened. A casino that held a valid UKGC licence at time of writing may have had it revoked. Payment methods or withdrawal limits described may no longer apply. When a review presents this information as current without any freshness signal or verification date, readers making real financial decisions are misled in exactly the way sec. 4.4 describes. The harm is not hypothetical: a user who deposits based on a bonus no longer available has been financially harmed by inaccurate content.
Supporting excerpt: "False dates for an election" [by structural analogy to outdated factual financial claims]
Citation: [SQEG 2025, sec. 4.4, p. 33]

## [CASINO-007] One-Sided Reviews With No Drawbacks
Category: Low/Lowest Signals for YMYL — Affiliate Bias / Low Quality
Section: 5.0 Low Quality Pages; 5.5 Unsatisfying Amount of Information about the Website or Content Creator
Pages: pp.58, 62-64
YMYL relevance: A casino review that presents only positive findings without acknowledging weaknesses, complaints, or material limitations fails the balanced and trustworthy content standard that applies to YMYL financial content.
Normalized note: Section 5.0 and 5.5 establish that low-effort, one-sided, or insufficiently informative content on YMYL topics can receive a Low rating even when it is not overtly deceptive. Casino affiliate reviews often exhibit this pattern: every casino reviewed receives high ratings, no casino receives a rating below four stars, and negative user feedback or regulatory sanctions are omitted entirely. This is not neutral or balanced; it is a form of content distortion driven by commercial incentive. The guideline's adoption-article Low example (generic, low-effort guidance on a consequential decision) is structurally analogous: a casino review that offers no genuine critical analysis of a platform that handles users' financial deposits is insufficiently expert and trustworthy for a YMYL financial topic.
Supporting excerpt: "should receive a Low rating"
Citation: [SQEG 2025, sec. 5.0 and 5.5, pp. 58, 62-64]

## [CASINO-008] Unverifiable Superlatives And Rankings
Category: Low/Lowest Signals for YMYL — Unsubstantiated Claims
Section: 3.4 Experience, Expertise, Authoritativeness, and Trust (E-E-A-T)
Pages: pp.25-26
YMYL relevance: Superlative claims such as "best casino in the UK," "highest payout rates," or "most trusted operator" are factual assertions in a YMYL financial context. Without verifiable methodology or evidence, they are unsubstantiated claims that undermine trust.
Normalized note: The trust dimension of E-E-A-T in sec. 3.4 requires that a page be reliable and honest, not just authoritative-looking. In casino affiliate content, superlative rankings are extremely common and almost never supported by disclosed methodology, independent verification, or transparent comparison criteria. When a page claims a casino is "number one for fast withdrawals" or "the most reliable operator" without citing evidence, user testing data, or an auditable comparison framework, the claim is unsubstantiated in the same way as other financial misinformation under sec. 4.4. This violation is especially significant because these claims often appear in page titles, H1 headings, and meta descriptions — the most prominent positions — where they disproportionately influence user decision-making before the review body is read.
Supporting excerpt: "The most important member ... is Trust"
Citation: [SQEG 2025, sec. 3.4, pp. 25-26]
