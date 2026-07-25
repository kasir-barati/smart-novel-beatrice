# ruff: noqa: RUF001

# P.S. => Postscript or "By the way, one more thing:"
# A-Are => this should sound like a stutter, though IDK how to represent that so Piper can sound like it is stuttering.
CHUNK_A = """
Mireya, Sylvia, and Valeria looked at Yuan with wide eyes, their gazes fixed on the cultivation techniques in his hands.

"A-Are those cultivation techniques…?" Sylvia asked in a surprised tone, her curiosity evident.

"That's right. These are for you. Once you learn them, you can start cultivating," Yuan said with a smile before handing each of them their specific techniques. They accepted them eagerly.

Valeria quickly opened her technique and began to read, but she couldn't understand a single thing. It was as if the content was obscured by a thick mist, making it impossible to decipher.

Immersed in this 'water' Michael heard the fading voice of the annoyed God.

"P.S. I gave you abilities based on your desires. It's unknown for now, but you'll find out about it soon enough.

And since I took you away from your very comfortable life, I have decided to reincarnate you as the youngest son of the richest family in the entire world. So, live a life of luxury, Mr. Stoic."


"""

# NOOOOOOOOOOO!!!!!!!!!!!!! -> this is a scream of frustration, despair, and disbelief. But how should I represent that so Piper can sound like screaming.
CHUNK_B = """
[Ding! You have successfully learned Heaven's Secret Arts]

<Heaven's Secret Arts>

<Rank: Divine>

<Mastery Level: 1>

<Description: Born from the chaos itself, Heaven's Secret Arts has nine Heavenly stages. Each state will unlock a new ability.>

___

<Heaven's First Secret Art— Consuming Heaven technique>

<Rank: Divine>

<Mastery Level: 1>

<Description: Absorbs 5 Qi per second. Can only be activated when sitting in the lotus position, as the level of mastery increases the Qi absorption rate will also increase.>

[There is a high possibility that this world doesn't have any plumbing.]

NOOOOOOOOOOO!!!!!!!!!!!!!

Michael had no choice but to scream out his frustrations about this world that the God put him into. There was nothing comfortable about living in this life!

...

[Uwaaaaa!]
"""

CHUNK_C = """
Aaaaah…

Kenjiro Sanchi’s cries echoed through the cave.

His strength was great, but his endurance was weak. The torment of his soul being churned was unbearable for him.

His clenched teeth almost shattered, blood filling the gaps.

Kenjiro Sanchi, rolling on the ground like a worm, didn’t notice that not far before him, the goddess statue suddenly opened its eyes.

This statue was carved by Kenjiro Sanchi. When carving the woman’s eyes, he had sculpted them in a slightly lowered, languid posture.

The pain of having this area directly shattered by a heavy blow even caused the power within the man’s body to surge uncontrollably, transforming into a hurricane sweeping the surroundings.

In the distance, glaciers shattered, dreamlike, crystal-clear ice shards scattering in the air, exceptionally beautiful.

Ahhhhhhh…

The shrill screams continued.

The sounds lingered around like restless spirits.

Terrifying canyons were torn open in the glacier.

After almost forcefully demanding Qin Chu hold her completely, the Little Goddess of Holy Light finally spoke: “Little sapling? That should be the World Tree.”

“World Tree?”

“Yes. The true body of the Earth Mother Goddess.”

Pfft…

Good grief.

Qin Chu just wanted to change the subject, but unexpectedly heard such explosive news.

He hadn’t expected the little sapling’s origin to be so exaggerated. The World Tree, the true body of the Earth Mother Goddess?
"""

print(len(CHUNK_A), len(CHUNK_B), len(CHUNK_C))

LONG_STORY_CHUNKS: list[str] = [CHUNK_A, CHUNK_B, CHUNK_C]
"""
In production it is client's responsibility to chunk a long text into smaller chunks before calling the normalizeTextForTts GraphQL mutation and then assembling it back into a complete text.
"""
