import streamlit as st
import pandas as pd
import threading
import queue
import time
import os
import io
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Website Analyzer",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 Website Analyzer")
st.caption("Detects ecommerce platforms, affiliate programs, and conversion events from a CSV of website URLs.")

# ─────────────────────────────────────────────
# CORE SCRAPING LOGIC (copied from your script)
# ─────────────────────────────────────────────

def analyze_website(page, url, timeout=30000):
    result = {
        'url': url,
        'status': None,
        'error_code': None,
        'ecommerce_platform': None,
        'affiliate_program': None,
        'conversion_event': None,
        'conversion_triggers': None
    }
    try:
        response = page.goto(url, timeout=timeout, wait_until='load')
        page.wait_for_timeout(2000)

        if response is None:
            result['status'] = 'Error'
            result['error_code'] = 'No response'
            return result

        result['status'] = 'Active'
        result['error_code'] = response.status

        if response.status != 200:
            return result

        html_text = page.content().lower()

        ecommerce_platforms = {
            'Shopify': ['shopify.com', 'cdn.shopify.com', 'myshopify.com'],
            'Bold': ['bold.com', 'boldcommerce.com', 'boldapps.net'],
            'Squarespace': ['squarespace.com', 'squarespace-cdn.com', 'sqsp.com'],
            'Stripe': ['stripe.com', 'js.stripe.com', 'stripe.network']
        }
        detected_platforms = []
        for platform, signatures in ecommerce_platforms.items():
            for sig in signatures:
                if sig in html_text:
                    detected_platforms.append(platform)
                    break
        result['ecommerce_platform'] = ', '.join(detected_platforms) if detected_platforms else None

        affiliate_programs = {
            'Commission Junction': ['cj.com', 'commission junction', 'commissionjunction'],
            'Rakuten': ['rakutenmarketing.com', 'rakuten advertising', 'linkshare.com'],
            'ShareASale': ['shareasale.com', 'shareasale'],
            'Tune': ['tune.com', 'hasoffers.com'],
            'AWIN': ['awin.com', 'awin1.com', 'zanox'],
            'CAKE': ['getcake.com', 'cake marketing'],
            'AspireIQ': ['aspireiq.com', 'aspire.io'],
            'CreatorIQ': ['creatoriq.com', 'creatoriq'],
            'Linkshare': ['linkshare.com', 'linksynergy.com'],
            'Linktrust': ['linktrust.com', 'linktrust'],
            'Pepperjam': ['pepperjam.com', 'pepperjamnetwork'],
            'Partnerize': ['partnerize.com', 'performancehorizon.com'],
            'Partnerstack': ['partnerstack.com', 'partnerstack'],
            'Tradedoubler': ['tradedoubler.com', 'tradedoubler'],
            'Affiliately': ['affiliately.com', 'affiliately'],
            'Avantlink': ['avantlink.com', 'avantlink'],
            'Everflow': ['everflow.io', 'everflow'],
            'Grin': ['grin.co', 'grin influencer'],
            'Tapfiliate': ['tapfiliate.com', 'tapfiliate'],
            'GoAffPro': ['goaffpro.com', 'goaffpro']
        }
        detected_programs = []
        for program, signatures in affiliate_programs.items():
            for sig in signatures:
                if sig in html_text:
                    detected_programs.append(program)
                    break
        result['affiliate_program'] = ', '.join(detected_programs) if detected_programs else None

        detected_events = []
        event_triggers = {}

        buttons = page.locator('button, a, input[type="submit"], input[type="button"]').all()
        interactive_text = []
        for button in buttons[:100]:
            try:
                text = button.inner_text(timeout=1000).lower().strip()
                if text:
                    interactive_text.append(text)
            except:
                pass
        itc = ' '.join(interactive_text)

        def check(indicators, event_name, fallback_html=None):
            found = [i for i in indicators if i in itc]
            if not found and fallback_html:
                found = [f"HTML: {x}" for x in fallback_html if x in html_text]
            if found:
                detected_events.append(event_name)
                event_triggers[event_name] = ', '.join(found[:3])

        check(['add to cart','add to bag','add-to-cart','addtocart','shopping cart','view cart','cart'],
              'Shopping cart', ['data-cart','cart.js','add-to-cart','addtocart'])
        check(['checkout','proceed to checkout','go to checkout','complete checkout','secure checkout'],
              'Checkout basket')
        check(['subscribe now','start subscription','subscribe and save','monthly subscription','subscribe'],
              'Subscription')
        check(['buy now','buy online','shop now','purchase now','order now','shop'], 'Online Sale')
        check(['purchase','complete purchase','buy product'], 'Purchase')
        check(['contact us','get in touch','request quote','request info','talk to sales','contact sales'], 'Lead')
        check(['create account','create your account','set up account','new account'], 'Account Creation')
        check(['sign up','signup','register','join now','get started','start free','join'], 'Account Signup')
        check(['first deposit','deposit now','add funds','fund account','make deposit'], 'First Deposit')
        check(['book appointment','schedule appointment','book now','schedule now','make appointment','reserve'],
              'Appointment Booked')
        check(['install app','download app','get the app','install now','app store','google play'],
              'Install', ['app-store-badge','google-play-badge'])
        check(['download now','free download','download guide','download ebook','download'], 'Download')
        check(['get approved','instant approval','application approved'], 'Application Approved')
        check(['apply now','submit application','apply today','complete application'], 'Application Submitted')

        result['conversion_event'] = ', '.join(list(dict.fromkeys(detected_events))) if detected_events else None
        if detected_events:
            result['conversion_triggers'] = ' | '.join(
                [f"{e}: [{event_triggers.get(e,'unknown')}]" for e in detected_events]
            )

        return result

    except PlaywrightTimeout:
        result['status'] = 'Timeout'
        result['error_code'] = 'Page Load Timeout'
        return result
    except Exception as e:
        result['status'] = 'Error'
        result['error_code'] = str(e)[:100]
        return result


def run_scraper(urls, delay, result_queue, stop_event):
    """Runs Playwright in a background thread and pushes results via queue."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()

            for i, url in enumerate(urls):
                if stop_event.is_set():
                    result_queue.put(('stopped', None))
                    break

                if pd.isna(url) or str(url).strip() == '':
                    result_queue.put(('result', {
                        'url': '', 'status': 'Empty', 'error_code': None,
                        'ecommerce_platform': None, 'affiliate_program': None,
                        'conversion_event': None, 'conversion_triggers': None
                    }))
                    continue

                clean_url = str(url).strip()
                if not clean_url.startswith(('http://', 'https://')):
                    clean_url = 'https://' + clean_url

                result_queue.put(('progress', f"[{i+1}/{len(urls)}] Analyzing: {clean_url}"))
                result = analyze_website(page, clean_url)
                result_queue.put(('result', result))

                if i < len(urls) - 1:
                    time.sleep(delay)

            browser.close()
        result_queue.put(('done', None))

    except Exception as e:
        result_queue.put(('error', str(e)))


# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
if 'results' not in st.session_state:
    st.session_state.results = []
if 'running' not in st.session_state:
    st.session_state.running = False
if 'done' not in st.session_state:
    st.session_state.done = False
if 'result_queue' not in st.session_state:
    st.session_state.result_queue = None
if 'stop_event' not in st.session_state:
    st.session_state.stop_event = None
if 'urls' not in st.session_state:
    st.session_state.urls = []
if 'log_lines' not in st.session_state:
    st.session_state.log_lines = []

# ─────────────────────────────────────────────
# SIDEBAR — SETTINGS
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    delay = st.slider("Delay between requests (seconds)", 1.0, 5.0, 2.0, 0.5)
    st.markdown("---")
    st.markdown("**Expected CSV columns:**")
    st.code("website / url / domain / URL / Website / Domain")
    st.markdown("---")
    st.markdown("**Detects:**")
    st.markdown("- 🛒 Ecommerce platforms (Shopify, Stripe, etc.)")
    st.markdown("- 🔗 Affiliate programs (CJ, AWIN, ShareASale, etc.)")
    st.markdown("- 🎯 Conversion events (checkout, signup, lead, etc.)")

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
uploaded_file = st.file_uploader("Upload your CSV of websites", type=["csv"])

if uploaded_file:
    try:
        df_input = pd.read_csv(uploaded_file)
        url_column = None
        for col in ['website', 'url', 'domain', 'Website', 'URL', 'Domain',
                    'final_url', 'original_url']:
            if col in df_input.columns:
                url_column = col
                break

        if url_column is None:
            st.error("❌ Could not find a URL column. Expected: website, url, or domain")
        else:
            urls = df_input[url_column].tolist()
            st.success(f"✅ Found **{len(urls)} websites** in column `{url_column}`")
            st.dataframe(df_input[[url_column]].head(5), use_container_width=True)

            col1, col2 = st.columns([1, 1])

            with col1:
                start_btn = st.button(
                    "▶️ Start Analysis",
                    disabled=st.session_state.running,
                    use_container_width=True,
                    type="primary"
                )
            with col2:
                stop_btn = st.button(
                    "⏹ Stop",
                    disabled=not st.session_state.running,
                    use_container_width=True
                )

            if start_btn and not st.session_state.running:
                st.session_state.results = []
                st.session_state.log_lines = []
                st.session_state.urls = urls
                st.session_state.running = True
                st.session_state.done = False
                q = queue.Queue()
                stop = threading.Event()
                st.session_state.result_queue = q
                st.session_state.stop_event = stop
                t = threading.Thread(target=run_scraper, args=(urls, delay, q, stop), daemon=True)
                t.start()
                st.rerun()

            if stop_btn and st.session_state.running:
                if st.session_state.stop_event:
                    st.session_state.stop_event.set()

    except Exception as e:
        st.error(f"Error reading CSV: {e}")

# ─────────────────────────────────────────────
# LIVE PROGRESS POLLING
# ─────────────────────────────────────────────
if st.session_state.running and st.session_state.result_queue:
    q = st.session_state.result_queue
    total = len(st.session_state.urls)

    # Drain queue
    try:
        while True:
            msg_type, payload = q.get_nowait()
            if msg_type == 'progress':
                st.session_state.log_lines.append(payload)
            elif msg_type == 'result':
                st.session_state.results.append(payload)
            elif msg_type in ('done', 'stopped', 'error'):
                st.session_state.running = False
                st.session_state.done = True
                if msg_type == 'error':
                    st.session_state.log_lines.append(f"❌ Error: {payload}")
                break
    except queue.Empty:
        pass

    completed = len(st.session_state.results)
    progress_val = completed / total if total > 0 else 0
    st.progress(progress_val, text=f"Analyzed {completed} / {total} websites")

    if st.session_state.log_lines:
        st.text(st.session_state.log_lines[-1])  # Show last log line

    if st.session_state.running:
        time.sleep(1)
        st.rerun()

# ─────────────────────────────────────────────
# RESULTS TABLE + DOWNLOAD
# ─────────────────────────────────────────────
if st.session_state.results:
    results_df = pd.DataFrame(st.session_state.results)
    total = len(st.session_state.urls)
    completed = len(results_df)

    if st.session_state.done:
        st.success(f"✅ Analysis complete — {completed} websites processed")

    # Summary metrics
    active = (results_df['status'] == 'Active').sum()
    has_ecom = results_df['ecommerce_platform'].notna().sum()
    has_aff = results_df['affiliate_program'].notna().sum()
    has_conv = results_df['conversion_event'].notna().sum()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total", completed)
    m2.metric("Active", active)
    m3.metric("Ecommerce", has_ecom)
    m4.metric("Affiliate", has_aff)
    m5.metric("Conversion Events", has_conv)

    st.markdown("---")

    # Filter options
    filter_col = st.selectbox(
        "Filter results by:",
        ["All", "Has ecommerce platform", "Has affiliate program", "Has conversion event", "Errors only"]
    )

    display_df = results_df.copy()
    if filter_col == "Has ecommerce platform":
        display_df = display_df[display_df['ecommerce_platform'].notna()]
    elif filter_col == "Has affiliate program":
        display_df = display_df[display_df['affiliate_program'].notna()]
    elif filter_col == "Has conversion event":
        display_df = display_df[display_df['conversion_event'].notna()]
    elif filter_col == "Errors only":
        display_df = display_df[display_df['status'] != 'Active']

    st.dataframe(
        display_df[['url', 'status', 'ecommerce_platform', 'affiliate_program', 'conversion_event']],
        use_container_width=True,
        height=400
    )

    # Download
    csv_buffer = io.StringIO()
    results_df.to_csv(csv_buffer, index=False)
    st.download_button(
        label="⬇️ Download Full Results CSV",
        data=csv_buffer.getvalue(),
        file_name="website_analysis_results.csv",
        mime="text/csv",
        use_container_width=True
    )

elif not st.session_state.running and not uploaded_file:
    st.info("👆 Upload a CSV to get started.")
