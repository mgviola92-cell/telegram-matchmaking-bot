"""Original, optional adult social conversation starters after mutual acceptance.

Single deterministic line per request; no user data, AI API, or database writes.
"""
STARTERS = (
    "🎵 မင်းလတ်တလော နားထောင်ဖြစ်နေတဲ့ သီချင်းလေး ရှိလား?",
    "🍜 အကြိုက်ဆုံး စားစရာလေးက ဘာလဲ?",
    "🎬 ကြိုက်တဲ့ ရုပ်ရှင်တစ်ကား အကြောင်း ပြောကြမလား?",
    "🌻 အားလပ်ချိန်ဆို ဘာလုပ်ရတာ ပိုပျော်လဲ?",
    "📚 အခုလတ်တလော စိတ်ဝင်စားနေတဲ့ ဝါသနာလေးက ဘာလဲ?",
    "🎮 နှစ်ယောက်အတူ ဆော့ရင် ပျော်မယ့် Game လေး ရှိလား?",
)


def after_mutual_acceptance(request_id):
    if not isinstance(request_id,int) or request_id<=0:
        raise ValueError("Valid resolved request ID required")
    return "\n\n💬 <b>စကားစကြည့်မလား?</b>\n"+STARTERS[request_id%len(STARTERS)]
