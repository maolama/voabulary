# app/llm/service.py
import time
import logging

logger = logging.getLogger(__name__)

class LLMService:
    """Strictly handles interactions with external LLM providers (e.g., Gemini, OpenAI)."""

    @staticmethod
    def generate_word_profile(word_text: str) -> list:
        """
        MOCK FUNCTION: Simulates calling an LLM to get the JSON profile.
        Returns hardcoded comprehensive data for specific test words, 
        and dynamic fallback data for anything else.
        """
        logger.info(f"Mocking LLM generation for: {word_text}")
        time.sleep(1.5) # Simulate network delay for UI testing
        
        target_word = word_text.strip().lower()

        # ==========================================
        # 1. MOCK DATA: "fast" (Multi-POS test: Adj, Adv, Verb, Noun)
        # ==========================================
        if target_word == "fast":
            return [
                {
                    "partOfSpeech": "adjective",
                    "ukPronunciation": "/fɑːst/",
                    "usPronunciation": "/fæst/",
                    "meanings": [
                        {
                            "definition": "Moving or capable of moving at high speed.",
                            "example": "He loves driving fast cars on the highway.",
                            "translation": "سریع",
                            "mnemonic": "Imagine a cheetah strapped to a rocket."
                        },
                        {
                            "definition": "(Of a clock or watch) showing a time ahead of the correct time.",
                            "example": "I missed my train because my watch is five minutes fast.",
                            "translation": "جلو (ساعت)",
                            "mnemonic": "The clock hands are running a marathon."
                        }
                    ],
                    "generalExamples": [
                        {
                            "example": "The fast pace of modern life can be exhausting.",
                            "translation": "سرعت تند زندگی مدرن می‌تواند خسته‌کننده باشد."
                        }
                    ],
                    "synonyms": ["quick", "rapid", "swift", "brisk"],
                    "antonyms": ["slow", "sluggish", "leisurely"],
                    "collocations": ["fast food", "fast track", "fast pace", "fast asleep"],
                    "notes": ["When used as 'fast asleep', it means deeply asleep, not sleeping quickly.", "Can also mean firmly fixed."],
                    "wordFamily": [{"word": "fastness", "pos": "noun"}]
                },
                {
                    "partOfSpeech": "verb",
                    "ukPronunciation": "/fɑːst/",
                    "usPronunciation": "/fæst/",
                    "meanings": [
                        {
                            "definition": "Abstain from all or some kinds of food or drink.",
                            "example": "Muslims fast from dawn to sunset during Ramadan.",
                            "translation": "روزه گرفتن",
                            "mnemonic": "Your stomach is moving 'fast' on empty."
                        }
                    ],
                    "generalExamples": [
                        {
                            "example": "She decided to fast for three days for health reasons.",
                            "translation": "او تصمیم گرفت برای دلایل سلامتی سه روز روزه بگیرد."
                        }
                    ],
                    "synonyms": ["starve", "diet", "go hungry"],
                    "antonyms": ["eat", "gorge", "feast"],
                    "collocations": ["fast completely", "fast regularly"],
                    "notes": ["Often associated with religious or medical contexts."],
                    "wordFamily": [{"word": "fasting", "pos": "noun"}]
                }
            ]

        # ==========================================
        # 2. MOCK DATA: "brake" (Noun vs Verb distinction)
        # ==========================================
        elif target_word == "brake":
            return [
                {
                    "partOfSpeech": "noun",
                    "ukPronunciation": "/breɪk/",
                    "usPronunciation": "/breɪk/",
                    "meanings": [
                        {
                            "definition": "A device for slowing or stopping a moving vehicle, typically by applying pressure to the wheels.",
                            "example": "He slammed on the brakes to avoid hitting the dog.",
                            "translation": "ترمز",
                            "mnemonic": "Don't 'break' your car, use the 'brake'."
                        }
                    ],
                    "generalExamples": [
                        {
                            "example": "The mechanic checked the brake pads during the service.",
                            "translation": "مکانیک لنت‌های ترمز را در طول سرویس بررسی کرد."
                        }
                    ],
                    "synonyms": ["stopping device", "curb", "restraint"],
                    "antonyms": ["accelerator", "gas pedal"],
                    "collocations": ["apply the brakes", "slam on the brakes", "brake pedal", "handbrake"],
                    "notes": ["Often confused with its homophone 'break'."],
                    "wordFamily": [{"word": "brakeless", "pos": "adjective"}]
                },
                {
                    "partOfSpeech": "verb",
                    "ukPronunciation": "/breɪk/",
                    "usPronunciation": "/breɪk/",
                    "meanings": [
                        {
                            "definition": "Make a moving vehicle slow down or stop by using a brake.",
                            "example": "She had to brake sharply when the traffic lights turned red.",
                            "translation": "ترمز گرفتن",
                            "mnemonic": ""
                        }
                    ],
                    "generalExamples": [
                        {
                            "example": "The driver braked hard, causing the tires to screech.",
                            "translation": "راننده محکم ترمز گرفت که باعث جیغ کشیدن لاستیک‌ها شد."
                        }
                    ],
                    "synonyms": ["slow down", "decelerate", "stop"],
                    "antonyms": ["accelerate", "speed up"],
                    "collocations": ["brake sharply", "brake suddenly", "brake hard"],
                    "notes": [],
                    "wordFamily": [{"word": "braking", "pos": "noun"}]
                }
            ]

        # ==========================================
        # 3. MOCK DATA: "strong" (Multiple nuances within one POS)
        # ==========================================
        elif target_word == "strong":
            return [
                {
                    "partOfSpeech": "adjective",
                    "ukPronunciation": "/strɒŋ/",
                    "usPronunciation": "/strɑːŋ/",
                    "meanings": [
                        {
                            "definition": "Having the power to move heavy weights or perform other physically demanding tasks.",
                            "example": "You must be very strong to lift that heavy box.",
                            "translation": "قوی (جسمانی)",
                            "mnemonic": "A bodybuilder holding up the world."
                        },
                        {
                            "definition": "Able to withstand great force or pressure; not easily broken.",
                            "example": "They built a strong defensive wall around the city.",
                            "translation": "مستحکم",
                            "mnemonic": "A castle made of solid steel."
                        },
                        {
                            "definition": "Very intense or prominent (e.g., relating to senses like smell or wind).",
                            "example": "There was a strong smell of burning rubber in the air.",
                            "translation": "شدید / غلیظ",
                            "mnemonic": "Coffee so dark it punches you in the face."
                        }
                    ],
                    "generalExamples": [
                        {
                            "example": "She has a strong personality and rarely backs down.",
                            "translation": "او شخصیت قوی‌ای دارد و به ندرت عقب‌نشینی می‌کند."
                        },
                        {
                            "example": "We need strong evidence to prove him guilty.",
                            "translation": "ما به مدارک محکمی برای اثبات گناهکاری او نیاز داریم."
                        }
                    ],
                    "synonyms": ["powerful", "muscular", "sturdy", "intense"],
                    "antonyms": ["weak", "fragile", "mild", "faint"],
                    "collocations": ["strong wind", "strong coffee", "strong evidence", "strong relationship"],
                    "notes": ["Can refer to physical strength, structural integrity, or sensory intensity."],
                    "wordFamily": [
                        {"word": "strongly", "pos": "adverb"},
                        {"word": "strength", "pos": "noun"},
                        {"word": "strengthen", "pos": "verb"}
                    ]
                }
            ]

        # ==========================================
        # 4. MOCK DATA: "mitigate" (Formal/Academic test case)
        # ==========================================
        elif target_word == "mitigate":
            return [
                {
                    "partOfSpeech": "verb",
                    "ukPronunciation": "/ˈmɪt.ɪ.ɡeɪt/",
                    "usPronunciation": "/ˈmɪt̬.ə.ɡeɪt/",
                    "meanings": [
                        {
                            "definition": "Make less severe, serious, or painful.",
                            "example": "Drainage schemes have helped to mitigate the flooding problem.",
                            "translation": "تسکین دادن / کاهش دادن",
                            "mnemonic": "Imagine a baseball 'mitt' catching a 'gate' falling on you, reducing the impact."
                        }
                    ],
                    "generalExamples": [
                        {
                            "example": "The government announced new policies to mitigate the effects of inflation.",
                            "translation": "دولت سیاست‌های جدیدی را برای کاهش اثرات تورم اعلام کرد."
                        },
                        {
                            "example": "Taking painkillers can mitigate the symptoms of the disease.",
                            "translation": "مصرف مسکن می‌تواند علائم بیماری را تسکین دهد."
                        }
                    ],
                    "synonyms": ["alleviate", "reduce", "diminish", "lessen", "ease"],
                    "antonyms": ["aggravate", "intensify", "worsen", "exacerbate"],
                    "collocations": ["mitigate the impact", "mitigate the effects", "mitigate risk"],
                    "notes": ["Highly formal.", "Commonly used in business, environmental, and legal contexts (e.g., 'mitigating circumstances')."],
                    "wordFamily": [
                        {"word": "mitigation", "pos": "noun"},
                        {"word": "unmitigated", "pos": "adjective"}
                    ]
                }
            ]

        # ==========================================
        # 5. DYNAMIC FALLBACK (For any other word you test)
        # ==========================================
        else:
            return [
                {
                    "partOfSpeech": "noun",
                    "ukPronunciation": f"/{target_word}/",
                    "usPronunciation": f"/{target_word}/",
                    "meanings": [
                        {
                            "definition": f"AI generated primary definition for '{target_word}'.",
                            "example": f"This is an example sentence using the word {target_word} in context.",
                            "translation": "ترجمه تستی",
                            "mnemonic": f"Imagine a giant {target_word} floating in space."
                        }
                    ],
                    "generalExamples": [
                        {
                            "example": f"I can't believe how many {target_word}s are here.",
                            "translation": "باورم نمیشه این همه از این کلمه اینجاست."
                        }
                    ],
                    "synonyms": [f"synonym-for-{target_word}"],
                    "antonyms": [f"antonym-for-{target_word}"],
                    "collocations": [f"heavy {target_word}", f"catch a {target_word}"],
                    "notes": ["This is fallback mock data generated by the backend."],
                    "wordFamily": [{"word": f"{target_word}ing", "pos": "verb"}]
                }
            ]