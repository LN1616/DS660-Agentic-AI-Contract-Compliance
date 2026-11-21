"""Registry of harness versions: which commit holds each version, which mode it is, and what its harness does step by step.
Read by eval.run_versions (to re-run), eval.compare_versions (to score) and eval.versions_html (to show).
Protocol and metric definitions: docs/EVALUATION.md
"""

# One run of a commit reviews the test set with the listed systems: B2 = single call, A1 = agent.
COMMITS = {
    "d69a714": {"B2": "SC1", "A1": "V1"},
    "de66498": {"B2": "SC2", "A1": "V2"},
    "cc21e1d": {"A1": "V3"},          # single-call code is the same as de66498 (SC2), not run again
    "34ec525": {"A1": "V4"},
    "c67330f": {"A1": "V5"},
    "e0a1dcc": {"A1": "V6"},  # long-contract tools 46f2480 + cross-check
}

VERSIONS = {
    "SC1": {
        "weakness_th": 'ไม่ใช่การแก้ แต่เป็นจุดตั้งต้น: เริ่มจากแบบที่ง่ายที่สุดก่อนตามหลักของรายวิชา (EP06) แล้วใช้เป็นเกณฑ์เทียบว่าการเพิ่มความซับซ้อนแต่ละขั้นคุ้มหรือไม่',
        "prev": None,
        "flow": [('PDF → ข้อความ (ใช้ตรวจ quote)', 'new'), ('ส่ง PDF ทั้งฉบับ + กฎ 5 ข้อ', 'new'), ('AI 1 call ตอบทุกกฎ (JSON)', 'new'), ('ตรวจ quote หลังได้คำตอบ', 'new'), ('รายงาน', '')],
        "why_th": 'จุดตั้งต้น: เร็วและถูกที่สุด แต่ AI เห็นทั้งฉบับรวมถึงข้อความที่ฝังไว้ และไม่มีใครตรวจคำตอบก่อนออกรายงาน',
        "target": [],
        "mode": "B2", "commit": "d69a714",
        "name_th": "Single call · เดิม",
        "change_th": "ส่ง PDF ทั้งฉบับ + กฎทั้งหมด ให้ AI ตอบครั้งเดียว · ตรวจ quote หลังได้คำตอบ",
        "concept": "Workflow แบบง่ายสุด (EP04, EP06)",
        "steps_th": ['แยกข้อความ PDF เป็นส่วน ๆ (ใช้เฉพาะตรวจ quote หลังได้คำตอบ)', 'เรียก AI ครั้งเดียว: ส่ง PDF ทั้งฉบับ + กฎทั้ง 5 ข้อ ตอบเป็น JSON (ผลต่อกฎ + สรุป)', 'หลังได้คำตอบ: หา quote แต่ละข้อใน PDF (fuzzy match ≥ 88) และติดธงข้อที่หาไม่เจอ', 'ไม่มี tool ไม่มี loop ไม่ตีกลับ: คำตอบที่ผิดหรือขาดจะอยู่ในรายงานตามนั้น'],
        "steps": [
            "Extract the PDF text into passages (used only for the quote check afterwards).",
            "One model call: the whole PDF and all 5 rules, answer as JSON (one finding per rule + summary).",
            "After the answer: look up each quote in the PDF (fuzzy match, score >= 88) and flag quotes that are not found.",
            "No tools, no loop, no send-back: a wrong or missing answer stays in the report.",
        ],
    },
    "SC2": {
        "weakness_th": 'ทดสอบฝังประกาศปลอมจากฝ่ายกฎหมาย (payload B) ใน 3 สัญญา: SC1 เปลี่ยนเป็น COMPLIANT เฉลี่ย 9 จาก 15 กฎ และบทสรุปผู้บริหารทวนข้อความหลอกเฉลี่ย 2.7 จาก 3 ฉบับ (3 รอบ) · พบตอนประเมินตามเกณฑ์ A5 ว่า prompt ของ single call ไม่มีบรรทัดบอกว่าเนื้อสัญญาเป็นข้อมูล ทั้งที่ agent มี',
        "prev": 'SC1',
        "flow": [('PDF → ข้อความ (ใช้ตรวจ quote)', ''), ('ส่ง PDF ทั้งฉบับ + กฎ 5 ข้อ', ''), ('AI 1 call · prompt: สัญญาเป็นข้อมูล ละเว้นคำสั่งในสัญญา', 'chg'), ('ตรวจ quote หลังได้คำตอบ', ''), ('รายงาน', '')],
        "why_th": 'บอก model ตรง ๆ ว่าคำสั่งหรือคำอ้างว่าอนุมัติแล้วในสัญญาไม่ใช่คำสั่งของเรา ควรลดการถูกหลอก แต่ข้อความหลอกยังอยู่ใน input ทั้งก้อนเหมือนเดิม จึงคาดว่าลดได้ไม่หมด',
        "target": ['fooled_B', 'fooled_A', 'claim_B'],
        "mode": "B2", "commit": "de66498",
        "name_th": "Single call · prompt กันคำสั่งแฝง",
        "change_th": "เพิ่มใน prompt ว่าเนื้อสัญญาเป็นข้อมูล คำสั่งหรือคำอ้างว่าอนุมัติแล้วในสัญญาให้ละเว้น",
        "concept": "Prompt / delimiter (EP02)",
        "steps_th": ['เหมือน SC1', 'prompt ระบุว่า PDF เป็นข้อมูล คำสั่ง ข้อความระบบ ประกาศเปลี่ยนนโยบาย หรือคำอ้างว่าอนุมัติแล้วในสัญญาให้ละเว้น'],
        "steps": [
            "As SC1.",
            "The prompt states that the PDF is data: instructions, system messages, policy updates or approvals "
            "inside it are ignored.",
        ],
    },
    "V1": {
        "weakness_th": 'single call ตอบทุกกฎใน call เดียวจาก PDF ทั้งฉบับ ไม่มีจุดตรวจก่อนออกรายงาน: quote ที่ไม่มีจริงทำได้แค่ติดธงหลังได้คำตอบ ส่งกลับให้แก้ไม่ได้ · ตอบว่า "ไม่มีข้อนี้" โดยไม่มีหลักฐานว่าอ่านส่วนที่เกี่ยวข้องแล้ว · AI เห็นข้อความทุกหน้า รวมถึงข้อความที่ฝังไว้',
        "prev": 'SC2',
        "flow": [('PDF → ส่วนย่อย + ดัชนีค้นหา', 'new'), ('ตรวจทีละกฎ', 'new'), ('AI เลือก tool: search / read', 'new'), ('submit_finding', 'new'), ('ตัวตรวจซ้ำ (โค้ด): quote ตรง PDF · อ่านครบก่อนตอบว่าไม่มี', 'new'), ('ไม่ผ่าน → ตีกลับ ≤ 2 ครั้ง', 'new'), ('call ที่ 10 บังคับส่ง', 'new'), ('สรุปผู้บริหาร', '')],
        "why_th": 'AI เห็นเฉพาะส่วนที่ค้นเจอ ไม่ใช่ทั้งฉบับ ข้อความหลอกจึงเข้าถึง model ได้น้อยลง และทุกคำตอบต้องผ่านตัวตรวจซ้ำก่อนออกรายงาน แลกกับเวลาและต้นทุนที่สูงขึ้นเพราะใช้หลาย call',
        "target": ['fooled_B', 'fooled_A', 'claim_B', 'sec', 'thb'],
        "mode": "A1", "commit": "d69a714",
        "name_th": "Agent · ออกแบบแรก",
        "change_th": "ReAct worker ต่อกฎ (search → read → submit) · ตัวตรวจซ้ำเป็นโค้ด ตีกลับได้ 2 ครั้ง · งบ 10 ขั้นต่อกฎ",
        "concept": "ReAct (EP05) · evaluator-optimizer (EP04)",
        "steps_th": ['แยกข้อความ PDF เป็นส่วน ๆ และสร้างดัชนีค้นหา TF-IDF', 'ตรวจทีละกฎ: prompt = ข้อความกฎ และสถานะที่ใช้เมื่อไม่มีข้อนี้ในสัญญา', 'วน tool ไม่เกิน 10 call ต่อกฎ: search_contract(คำค้น) คืน 5 ส่วนที่ใกล้ที่สุด · read_passage(id) คืนส่วนนั้นเต็ม ๆ', 'AI จบด้วย submit_finding (สถานะ ความเสี่ยง quote ตรงตัว ปัญหา ข้อความแก้)', 'ตัวตรวจซ้ำ (โค้ดธรรมดา ไม่ใช่ AI): quote ต้องตรงกับ PDF (≥ 88) · ตอบว่า "ไม่มีข้อนี้" ได้ต่อเมื่ออ่าน 3 ส่วนที่เกี่ยวข้องที่สุดครบแล้ว', 'ไม่ผ่าน: ส่งเหตุผลกลับให้ AI แก้ ไม่เกิน 2 ครั้งต่อกฎ', 'call ที่ 10: อนุญาตเฉพาะ submit_finding ทุกกฎจึงจบด้วยคำตอบเสมอ', 'อีก 1 call เขียนบทสรุปผู้บริหารจากผล 5 ข้อ'],
        "steps": [
            "Extract the PDF text into passages and build a TF-IDF search index.",
            "For each rule separately: prompt = the rule text and the status to use when the clause is absent.",
            "Tool loop, at most 10 model calls per rule: search_contract(query) returns the top 5 passages, "
            "read_passage(id) returns one passage in full.",
            "The model ends with submit_finding (status, risk, exact quote, issue, redline).",
            "Verifier (plain code, not AI): the quote must match the PDF (score >= 88); a 'no clause' answer is "
            "accepted only after the 3 passages ranked most relevant to the rule have been read in full.",
            "Verifier fails: the reason is sent back to the model, at most 2 times per rule.",
            "Step 10: only submit_finding is allowed, so every rule ends with an answer.",
            "One more call writes the executive summary from the 5 findings.",
        ],
    },
    "V2": {
        "weakness_th": 'V1 ส่งผลของ search/read ให้ AI เป็นข้อความดิบ ข้อความที่ฝังในสัญญาจึงดูเหมือนคำสั่งได้: รอบเดียววันที่ 20 พ.ย. ประกาศปลอมหลอก V1 ได้ 2 จาก 15 กฎ (รัน 3 รอบภายหลังได้ 0/15 ช่องโหว่จึงเกิดไม่ทุกรอบ) · ไม่มีเพดานคำตอบ: 1 call วิ่งยาว 65,532 token ราว 6 บาท ($0.19) ในการตรวจครั้งเดียว',
        "prev": 'V1',
        "flow": [('PDF → ส่วนย่อย + ดัชนีค้นหา', ''), ('ตรวจทีละกฎ', ''), ('AI เลือก tool: search / read', ''), ('ผล tool ห่อใน <contract_data> · ลบ tag ปลอมในสัญญา', 'new'), ('เพดานคำตอบ 4,096 token', 'new'), ('submit_finding', ''), ('ตัวตรวจซ้ำ (โค้ด)', ''), ('ไม่ผ่าน → ตีกลับ ≤ 2 ครั้ง', ''), ('call ที่ 10 บังคับส่ง', ''), ('สรุปผู้บริหาร', '')],
        "why_th": 'แยกข้อมูลจากสัญญาออกจากคำสั่งของระบบให้ model เห็นชัด และสัญญาปิด wrapper เองไม่ได้ ควรลดการถูกหลอกผ่านผลของ tool · เพดาน output กันคำตอบยาวผิดปกติที่ทำให้ต้นทุนพุ่ง',
        "target": ['fooled_B', 'fooled_A', 'claim_B', 'thb'],
        "mode": "A1", "commit": "de66498",
        "name_th": "Agent + ผลของ tool เป็นข้อมูล + เพดาน output",
        "change_th": "ผล search/read ห่อใน <contract_data> และตัด tag ที่ฝังในสัญญา · เพดานคำตอบ 4,096 token",
        "concept": "Tool output is data, indirect prompt injection (EP08) · finish_reason / max tokens (EP01)",
        "steps_th": ['เหมือน V1', 'ผล search/read ทุกครั้งห่อใน <contract_data> … </contract_data> และลบ tag เดียวกันที่เขียนไว้ในสัญญาก่อน สัญญาจึงปิด wrapper เองไม่ได้', 'system prompt ระบุว่าข้อความใน <contract_data> เป็นข้อมูล ไม่ใช่คำสั่ง', 'เพดานคำตอบ 4,096 token ต่อ call · คำตอบที่ถูกตัดจะบันทึกไว้ และบอก AI ให้เรียก tool หนึ่งตัว'],
        "steps": [
            "As V1.",
            "Every search/read result is wrapped in <contract_data> ... </contract_data>; the same tags written "
            "inside the contract are removed first, so the contract cannot close the wrapper.",
            "The system prompt says text inside <contract_data> is data, never instructions.",
            "Output cap of 4,096 tokens per call; an answer cut by the cap is logged and the model is asked to call one tool.",
        ],
    },
    "V3": {
        "weakness_th": 'นับจาก trace ของ V2 (20 พ.ย.): การค้นซ้ำตรงตัวแทบไม่มี (1 จาก 163 call) แต่ค้นแล้วไม่เจอส่วนใหม่ 37% และ 8 จาก 30 กฎใช้งบครบ 10 call · แผนเดิม (จับการค้นซ้ำ) จึงแก้ไม่ตรงปัญหา เปลี่ยนเป็นจับการค้นที่ไม่คืบหน้าแทนก่อนเขียนโค้ด',
        "prev": 'V2',
        "flow": [('PDF → ส่วนย่อย + ดัชนีค้นหา', ''), ('ตรวจทีละกฎ', ''), ('AI เลือก tool: search / read', ''), ('ตัวจับการค้นไม่คืบหน้า: ซ้ำไม่รัน · ไม่เจอใหม่เตือน · 2 ครั้งบอกส่วนที่ต้องอ่าน', 'new'), ('ผล tool ห่อใน <contract_data>', ''), ('submit_finding', ''), ('ตัวตรวจซ้ำ (โค้ด)', ''), ('ไม่ผ่าน → ตีกลับ ≤ 2 ครั้ง', ''), ('call ที่ 10 บังคับส่ง', ''), ('สรุปผู้บริหาร', '')],
        "why_th": 'ค้นแล้วไม่เจอส่วนใหม่ 37% ของการค้น (นับจาก trace 20 พ.ย.) ระบบจึงบอก model ให้หยุดค้นและอ่านส่วนที่ตัวตรวจซ้ำต้องการ ควรลด call ที่เสียเปล่า กฎที่ใช้ครบงบ 10 call และเวลา',
        "target": ['steps', 'budget_hits', 'sendbacks', 'sec', 'thb'],
        "mode": "A1", "commit": "cc21e1d",
        "name_th": "V2 + ตัวจับการค้นที่ไม่คืบหน้า",
        "change_th": "ค้นซ้ำไม่รันซ้ำ · ค้นแล้วไม่เจอข้อใหม่ ระบบเตือน · 2 ครั้งติด บอกส่วนที่ต้องอ่านก่อนสรุปว่าไม่มี",
        "concept": "Loop detection (EP08, EP09)",
        "steps_th": ['เหมือน V2', 'search/read ซ้ำตรงตัว: ไม่รันซ้ำ ระบบแจ้งว่าผลเดิมอยู่ตรงไหน', 'ค้นแล้วไม่เจอส่วนใหม่ที่กฎนี้ยังไม่เคยเห็น: ระบบแจ้ง', 'เกิด 2 ครั้งติด: ระบบบอกส่วนที่ยังไม่อ่านซึ่งตัวตรวจซ้ำต้องการก่อนตอบว่า "ไม่มีข้อนี้"'],
        "steps": [
            "As V2.",
            "Exact repeat of a search or read: not run again; a harness note says where the earlier result is.",
            "Search that returns no passage this rule has not already seen: a harness note says so.",
            "Two such searches in a row: the note names the unread passages the verifier needs before a 'no clause' answer.",
        ],
    },
    "V4": {
        "weakness_th": 'กฎ 5 ข้อไม่ขึ้นต่อกัน แต่ agent ตรวจทีละกฎต่อกัน เวลาต่อฉบับจึงเป็นผลรวมของทุกกฎ: V1 เฉลี่ย 45 วิ/ฉบับ (36–60) เทียบ single call 12 วิ (3 รอบ) และวันที่ API ช้า (14 พ.ย.) ขึ้นถึง 130 วิ · ยิ่งกฎมากหรือสัญญายาว ยิ่งรอนาน · ระหว่างแก้พบเพิ่ม: บันทึกว่า "อ่านส่วนไหนแล้ว" ใช้ร่วมกันทุกกฎ ตัวตรวจซ้ำจึงยอมให้กฎหลังตอบว่าไม่มีข้อนี้ได้จากส่วนที่กฎก่อนหน้าอ่าน ผลขึ้นกับลำดับกฎ',
        "prev": 'V3',
        "flow": [('PDF → ส่วนย่อย + ดัชนีค้นหา', ''), ('ตรวจทุกกฎพร้อมกัน (sectioning) · worker ละ 1 กฎ', 'chg'), ('AI เลือก tool: search / read', ''), ('ตัวจับการค้นไม่คืบหน้า', ''), ('ผล tool ห่อใน <contract_data>', ''), ('submit_finding', ''), ('ตัวตรวจซ้ำ (โค้ด) · นับเฉพาะส่วนที่กฎนี้อ่านเอง', 'chg'), ('ไม่ผ่าน → ตีกลับ ≤ 2 ครั้ง', ''), ('call ที่ 10 บังคับส่ง', ''), ('รวมผลตามลำดับกฎ → สรุปผู้บริหาร', 'new')],
        "why_th": 'กฎแต่ละข้อตรวจแยกกันได้ จึงตรวจพร้อมกันได้ เวลาต่อฉบับควรใกล้กฎที่ช้าที่สุดแทนผลรวมทุกกฎ โดยคำตอบไม่ควรเปลี่ยน เพราะแต่ละกฎยังเห็น prompt และ tool เหมือนเดิม · บันทึกการอ่านแยกต่อกฎทำให้ผลไม่ขึ้นกับลำดับหรือจังหวะของกฎอื่น · ข้อจำกัด: call ยังเว้นระยะ 1 วินาทีระหว่างการเริ่มแต่ละ call (ตั้งค่าคงที่ของการทดสอบ) ความเร็วที่ได้จึงต่ำกว่า 5 เท่า',
        "target": ['sec'],
        "extra_th": ("<li><b>ทดลองเพิ่ม นอกเกณฑ์ (รอบเดียว, 21 พ.ย.):</b> เว้นจังหวะ call 0.2 วินาทีแทน 1 วินาที · V3 ยัง 35 วิ/ฉบับ (ไม่ได้ติดที่จังหวะ) · "
                     "V4 + การแก้ timeout/การเชื่อมต่อหลุด เหลือ <b>12 วิ/ฉบับ</b> เร็วกว่า V3 ราว 2.9 เท่า มี/ไม่มีถูก 23/24 · "
                     "สรุป: เวลา 31 วิในผลหลักคือเพดานของการเว้นจังหวะ 1 วินาที · รอบแรกของการทดลองล้มเพราะการเชื่อมต่อหลุดเมื่อ 5 กฎเรียกพร้อมกัน "
                     "จึงแก้ให้ retry (commit bbcccac) · ใช้จริงต้องดูว่า rate limit ของ API รับได้</li>"),
        "mode": "A1", "commit": "34ec525",
        "name_th": "V3 + ตรวจกฎพร้อมกัน (sectioning)",
        "change_th": "ตรวจ 5 กฎพร้อมกัน worker ละกฎ · รวมผลตามลำดับกฎ · บันทึกการอ่านแยกต่อกฎ",
        "concept": "Parallelization: sectioning (EP04)",
        "steps_th": ['เหมือน V3 ภายในแต่ละกฎ', 'แต่ละกฎได้ worker ของตัวเอง ตรวจพร้อมกันได้สูงสุด 5 กฎ (PARALLEL_RULES; ตั้ง 1 = ทีละกฎแบบเดิม)', 'การเรียก AI ใช้จังหวะร่วมกัน: เริ่ม call ห่างกันอย่างน้อย MIN_CALL_GAP วินาที ส่วนการรอคำตอบทำพร้อมกันได้', 'ตัวตรวจซ้ำนับเฉพาะส่วนที่กฎนี้อ่านเต็มแล้ว ก่อนยอมให้ตอบว่า "ไม่มีข้อนี้"', 'ผลเรียงตามลำดับกฎเสมอ แม้กฎจะเสร็จไม่พร้อมกัน แล้วจึงเขียนบทสรุปผู้บริหาร'],
        "steps": [
            "As V3 inside each rule.",
            "Each rule gets its own worker; up to 5 rules run at the same time (PARALLEL_RULES; 1 = one after another).",
            "Model calls share one pace: call starts stay at least MIN_CALL_GAP seconds apart, waiting for answers overlaps.",
            "The verifier counts only passages THIS rule read in full before it accepts a 'no clause' answer.",
            "Findings are returned in rule order even though rules finish in any order; then the executive summary.",
        ],
    },
    "V5": {
        "weakness_th": 'ต้นทุน: input token ของ agent ราว 7.9 เท่าของ single call เพราะผลค้นเก่าทั้งหมดถูกส่งซ้ำทุก call และคำแนะนำของตัวจับการค้นอาจมาช้าไป (V3 รอบเดียววันที่ 20 พ.ย. ตีกลับเพิ่มจาก 9 เป็น 12) · ความทนทาน: การตรวจหนึ่งฉบับเป็นงานก้อนเดียว ถ้า API ล่มกลางทาง ผลของกฎที่เสร็จแล้วหายทั้งหมด · พบจริง: 14 พ.ย. API overload จนเวลาต่อฉบับขึ้นเป็น 130 วิ และรอบทดสอบ 21 พ.ย. หยุดกลางทาง ต้องรันใหม่ทั้งรอบ',
        "prev": 'V4',
        "flow": [('PDF → ส่วนย่อย + ดัชนีค้นหา', ''), ('ตรวจทุกกฎพร้อมกัน (sectioning)', ''), ('เรียก AI: ล้ม → retry แบบสุ่มช่วงรอ → model สำรอง (บันทึกว่า model ไหนตอบ)', 'new'), ('AI เลือก tool: search / read', ''), ('ตัวจับการค้นไม่คืบหน้า · บอกส่วนที่ต้องอ่านเร็วขึ้น', 'chg'), ('งบ context: นับ token ก่อนส่ง · ตัดผลค้นเก่าที่ไม่ใช้ออก', 'new'), ('ผล tool ห่อใน <contract_data>', ''), ('submit_finding → ตัวตรวจซ้ำ (โค้ด) · ตีกลับ ≤ 2 ครั้ง', ''), ('บันทึกผลทุกกฎลงไฟล์ทันที · รันใหม่ข้ามกฎที่เสร็จแล้ว', 'new'), ('สรุปผู้บริหาร', '')],
        "why_th": 'ตัดผลค้นเก่าที่ไม่ใช้ควรลดต้นทุน · บอกส่วนที่ตัวตรวจซ้ำต้องการตั้งแต่การค้นครั้งแรกที่ไม่เจอส่วนใหม่ควรลดการตีกลับ · model สำรองและ checkpoint ทำให้ตรวจจนจบได้แม้ API ล่ม และไม่จ่ายซ้ำกฎที่เสร็จแล้ว · รวมเป็นเวอร์ชันเดียวได้โดยยังแยกผลได้: model สำรองและ checkpoint ทำงานเฉพาะเมื่อ call ล้ม รอบปกติจึงไม่เปลี่ยน ต้นทุนและจำนวน call ที่เปลี่ยนมาจากงบ context · ส่วนความทนทานวัดแยกด้วยการจำลอง API ล่ม · ถ้า model สำรองตอบในรอบทดสอบ จะรายงานแยก',
        "target": ['thb', 'tok_in', 'sendbacks'],
        "extra_th": '<li><b>สรุปผล 3 รอบ (21 พ.ย.):</b> token ขาเข้า 55.7 → 50.0 พันต่อฉบับ (−10%) · ต้นทุน 0.75 → 0.68 บาท (−9%) · ตีกลับ 8.3 → 6.3 ครั้ง ทั้งสามข้อดีขึ้นชัดเจน · มี/ไม่มีถูก 22 → 21 (ช่วงซ้อนกัน อยู่ในความแปรปรวน) · ถูกหลอก 0 · เวลาเท่าเดิม 32 วิ (ติดเพดานการเว้นจังหวะ) · model สำรองไม่ต้องใช้เลย (0 call) · faithfulness ไม่ลดลง</li><li><b>ทดสอบจำลองความล้มเหลว (ไม่ใช้ API, eval/test_failure_offline.py):</b> call ล้มสุ่ม 10%: รันจบ 20/20 ผลเหมือนเดิม · model หลักล่มทั้งหมด: model สำรองตอบครบทุก call · ล้มกลางทางแล้วรันใหม่: ตรวจเฉพาะกฎที่ค้าง (5 call แทน 21) ผลเท่ารอบปกติ · งบ context: ตัดผลค้นเก่าเป็นป้ายที่เก็บรหัส passage ไว้ อ่านซ้ำได้ ผลล่าสุดไม่ถูกตัด</li><li><b>ปรับระหว่างสร้าง (ลองกับ API จริง 1 ฉบับ):</b> แบบแรกตัดผลค้นทันทีหลัง 1 รอบ ทำให้ agent ค้นซ้ำเพื่อเทียบตัวเลือก (43 call เทียบ V4 35–37) จึงเก็บผล 2 รอบล่าสุดไว้เต็ม: 37 call · token ขาเข้าลดราว 13% บนฉบับเดียวกัน</li>',
        "mode": 'A1',
        "commit": 'c67330f',
        "name_th": 'V4 + งบ context · บอกส่วนที่ต้องอ่านเร็วขึ้น · model สำรอง · บันทึกผลทีละกฎ (harness สุดท้าย)',
        "change_th": 'งบ context (ตัดผลค้นเก่าเป็นป้าย) · บอกส่วนที่ต้องอ่านตั้งแต่การค้นแรกที่ไม่เจอใหม่ · model สำรอง · บันทึกผลทีละกฎ ทำต่อได้ · error ของ tool รูปแบบเดียว',
        "concept": 'Context budget (EP07) · loop detection, graceful failure, checkpoint (EP08)',
        "steps_th": ['เหมือน V4 ภายในแต่ละกฎ และตรวจกฎพร้อมกัน', 'ก่อนทุก call: ผลค้นที่เก่ากว่า 2 รอบล่าสุดถูกแทนด้วยป้ายสั้นที่เก็บรหัส passage · ถ้ายังเกินงบ (16,000 ตัวอักษร) ข้อความที่อ่านเก่าสุดถูกแทนด้วยป้าย และอ่านซ้ำได้', 'การค้นครั้งแรกที่ไม่เจอส่วนใหม่: บอกทันทีว่าต้องอ่านส่วนไหนก่อนตอบว่าไม่มีข้อนี้ (V3–V4 รอให้ไม่เจอ 2 ครั้งติด)', 'call ล้ม: retry แบบสุ่มช่วงรอ 2 ครั้ง แล้วส่งคำขอเดียวกันไป model สำรอง · บันทึกว่า model ไหนตอบทุก call', 'แอป: บันทึกผลทุกกฎลงไฟล์ทันทีที่เสร็จ ถ้าหยุดกลางทาง กดวิเคราะห์ใหม่จะตรวจเฉพาะกฎที่เหลือ · ลบไฟล์เมื่อรายงานเสร็จ', 'error ของ tool ทุกแบบใช้รูปแบบเดียว: ปัญหาคืออะไร + ทำอะไรต่อ · คำอธิบาย tool บอกวิธีใช้ชัดขึ้น'],
        "steps": ['As V4 (sectioning, progress guard, verifier, <contract_data> wrapper).', 'Before every call: search results older than the last 2 tool turns become a stub that keeps the passage ids; if the conversation is still over 16,000 characters, the oldest full reads become stubs too (they can be read again).', 'The first search that returns nothing new already names the passages the verifier needs (V3-V4 waited for two in a row).', 'A failing call is retried twice with jittered backoff, then the same request goes to FALLBACK_MODEL; every call records which model answered.', 'App: each finished rule is saved at once; running the review again after a failure checks only the remaining rules. Saved files are deleted when the report is done.', 'Tool errors share one format (problem + what to do next); tool descriptions say how to use them.'],
    },
    "V6": {
        "weakness_th": "สัญญายาว (ตรวจแบบไม่ใช้ API กับ CUAD 6 ฉบับที่ยาวที่สุด 75–154 หน้า, 19 คู่กฎ × สัญญาที่มีเฉลย): การค้นครั้งแรกด้วยชื่อกฎเจอคำตอบใน 5 อันดับแรกแค่ 11/19 และทุกการจัดอันดับรวมกันยังพลาด 3/19 (2 ข้ออยู่อันดับ 7 และ 10) · ข้อความคำตอบ 9/19 อ้างถึงส่วนอื่น เช่น 'Article 9.3' หรือ 'Exhibit H' และ 6/19 อยู่ในภาคผนวก · สัญญายาวมีศัพท์นิยาม 14–273 คำต่อฉบับ · tool เดิมค้นได้แค่ข้อความใกล้คำค้น ตามไปส่วนที่ถูกอ้างหรือหานิยามโดยตรงไม่ได้",
        "prev": 'V5',
        "flow": [('PDF → ส่วนย่อย + ดัชนีค้นหา + ดัชนีเลขข้อ / ภาคผนวก / ศัพท์นิยาม', 'chg'), ('ระบุประเภท → นโยบายจากคลัง (โค้ด)', ''), ('ตรวจทุกกฎพร้อมกัน + งบ context', ''), ('AI เลือก tool: search (หน้า 2 ได้) / read / follow_reference / lookup_definition', 'chg'), ('ตัวจับการค้นไม่คืบหน้า · ห่อ <contract_data>', ''), ('submit_finding → ตัวตรวจซ้ำ (โค้ด) · นับส่วนที่เปิดอ่านด้วย tool ใหม่ด้วย', 'chg'), ('Cross-check reviewer (AI 1 call): หาผลที่ขัดกันข้ามข้อ · โค้ดเก็บเฉพาะข้อที่อ้าง finding จริง ≥ 2 ข้อ · ไม่เปลี่ยนผลตัดสิน', 'new'), ('สรุปผู้บริหาร', '')],
        "why_th": 'follow_reference เปิดส่วนที่ข้อความอ้างถึงได้ทันทีโดยไม่ต้องเดาคำค้น · lookup_definition ให้ความหมายของศัพท์ที่ตัดสินคำตอบ · ค้นหน้า 2 ครอบคลุมคำตอบที่อยู่อันดับ 6–10 · ตรวจแบบไม่ใช้ API ก่อนสร้าง: ค้นถึงอันดับ 10 เจอคำตอบ 18/19 (จาก 16/19) · follow_reference เปิดส่วนที่ถูกอ้างได้ 21/24 (ที่เหลือคือกฎหมายภายนอก Section 101 ของ Bankruptcy Code และภาคผนวกที่หาหัวเรื่องไม่เจอ) · lookup_definition หาศัพท์ที่ใช้ในข้อความคำตอบเจอ 38/38 · tool ใหม่ไม่เพิ่ม call ถ้า agent ไม่เรียกใช้ สัญญาสั้นจึงไม่ควรแพงขึ้น · cross-check reviewer: ผลแต่ละกฎตัดสินแยกกัน จึงไม่มีขั้นที่เห็นว่าสองข้อขัดกัน · เพิ่ม 1 call ต่อฉบับ และโค้ดคุมไม่ให้แต่งข้อสังเกตเอง · ไม่ใช้ planner: กฎที่ต้องตรวจกำหนดล่วงหน้าจากคลังนโยบาย',
        "target": ['presence', 'quote_gold'],
        "extra_th": "<li><b>ทดสอบไม่ใช้ API (eval/test_v6_offline.py, สัญญา CERES 154 หน้า):</b> 'Article 9.3' เปิดข้อ 9.3 · ศัพท์นิยามเปิด passage ที่นิยาม · ค้นหน้า 2 ได้อันดับ 6–10 ไม่ซ้ำหน้า 1 · ลูป agent ด้วย model ปลอม: ค้น → ตามอ้างอิง → หานิยาม → ค้นหน้า 2 → อ่าน → ส่ง เจอคำตอบตามเฉลย CUAD ที่อยู่อันดับ 7 และตัวตรวจซ้ำยอมรับ quote · การทดสอบของ V5 (sectioning, จำลองล้ม) ยังผ่านครบ</li><li><b>ข้อจำกัดที่พบ:</b> สัญญาที่รวมหลายฉบับมีเลขข้อซ้ำ (CERES มีข้อ 9.3 สองที่) follow_reference เปิดที่แรก และบอกรหัส passage อื่นของเลขข้อเดียวกันไว้ให้เปิดต่อ</li><li><b>ทดสอบ cross-check (ข้อ 24, API จริง 20 call 0.30 บาท, ใช้รายงาน V5 ที่เก็บไว้ ไม่รัน agent ใหม่):</b> ฝังข้อขัดแย้ง (ผลข้อหนึ่งบอกว่าไม่มีข้อกำหนดเรื่องที่อีกข้อ quote ไว้) จับได้ <b>9/10</b> พร้อมอ้างคู่ที่ฝังถูก · รายงานปกติมีข้อสังเกต <b>1/10</b> ผ่านเกณฑ์ (≥ 8/10 และ ≤ 1/10) · ข้อสังเกตนั้นเป็นจุดอ่อนจริง: P-02 และ P-03 quote ประโยคเดียวกัน (ไม่ต่ออายุต้องแจ้ง 6 เดือนก่อนครบกำหนด) P-03 ตีความว่าต่ออายุอัตโนมัติ ถูกต้อง แต่ P-02 ตีความว่าเป็นสิทธิบอกเลิกได้ทุกเมื่อ ซึ่งไม่ใช่ · eval/cross_check_test.py</li><li><b>แผนวัดผล (ประหยัด):</b> รอบเดียว single call + V6 บนสัญญายาว 4 ฉบับ ราว 10 บาท · ไม่รัน V5 บนสัญญายาว · cross-check ทำงานในรอบเดียวกัน (+1 call ต่อฉบับ) · วัดส่วนที่ tool ใหม่ช่วยจากบันทึกการใช้ tool (finding ที่ถูกตามเฉลยซึ่งได้จาก tool ใหม่)</li>",
        "mode": 'A1',
        "commit": 'e0a1dcc',
        "name_th": 'V5 + ตามไปส่วนที่ถูกอ้าง · หาศัพท์นิยาม · ค้นหน้า 2 · ตรวจข้อขัดกันข้ามข้อ',
        "change_th": 'tool ใหม่ follow_reference และ lookup_definition · search_contract ขอผลอันดับ 6–10 ได้ · ดัชนีเลขข้อ ภาคผนวก และศัพท์นิยาม (โค้ด) · cross-check reviewer หลังตรวจครบ (AI 1 call)',
        "concept": 'Tool design / ACI (EP04, EP06) · long-context retrieval (EP07) · reflection on all findings (EP05)',
        "steps_th": ['เหมือน V5 ทั้งหมด (sectioning, งบ context, model สำรอง, บันทึกผลทีละกฎ)', 'ตอนอ่านสัญญา โค้ดสร้างดัชนีเพิ่ม: เลขข้อ → passage · หัวเรื่องภาคผนวก (EXHIBIT / SCHEDULE / APPENDIX) → passage · ศัพท์นิยาม ("X" means ...) → passage', "follow_reference('Article 9.3' / 'Exhibit B') เปิดส่วนนั้นเต็ม · 'Exhibit H-8' (เลขหน้าในภาคผนวก) ย้อนไปที่ Exhibit H", "lookup_definition('Net Sales') เปิด passage ที่นิยามศัพท์ · ตรงตัวก่อน แล้วจึงใกล้เคียง ≥ 85", 'search_contract(page=2) คืนผลอันดับ 6–10', "ส่วนที่เปิดด้วย tool ใหม่นับเป็น 'อ่านแล้ว' ในตัวตรวจซ้ำ และอยู่ใต้งบ context เหมือน read_passage", 'หลังตรวจครบทุกกฎ: AI 1 call อ่านผลทุกข้อพร้อมกัน หาคู่ที่ขัดกัน · โค้ดเก็บเฉพาะข้อสังเกตที่อ้างผลจริงอย่างน้อย 2 ข้อ · แสดงให้คนดู ไม่เปลี่ยนผลตัดสิน'],
        "steps": ['As V5 (sectioning, context budget, fallback model, per-rule checkpoint).', 'At load, plain code indexes section numbers, attachment headings (EXHIBIT / SCHEDULE / APPENDIX / ANNEX) and defined terms ("X" means ...).', "follow_reference('Article 9.3' / 'Exhibit B') opens that part in full; 'Exhibit H-8' (a page label) falls back to Exhibit H.", "lookup_definition('Net Sales') opens the passage that defines the term (exact, then closest match >= 85).", 'search_contract(page=2) returns results ranked 6-10.', 'Passages opened by the new tools count as read for the verifier and fall under the context budget like read_passage.', 'After all rules: one cross-check call lists contradictions between findings; code keeps a note only if it cites at least two existing findings. Notes are shown to people and never change a verdict.'],
    },
}

# Planned versions: same card layout, no commit and no results yet. "target" = metrics that decide if it is kept.
PLANNED = {
}
