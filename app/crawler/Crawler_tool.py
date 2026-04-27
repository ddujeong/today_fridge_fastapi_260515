from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
  ElementClickInterceptedException,
  TimeoutException,
  NoSuchElementException,
  StaleElementReferenceException,
  WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait
import time
import random
from datetime import datetime


class Crawler:
  def __init__(self,target_url="https://www.10000recipe.com/recipe/list.html"):
    chrome_options = Options()
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    self.driver = webdriver.Chrome(options=chrome_options)
    self.target_url = target_url
    self.driver.get(self.target_url)
    self.debug = True

    self.speed = {
      "super slow": 2.0,
      "slow": 1.0,
      "normal": 0.5,
      "fast": 0.1,
      "super fast": 0.05,
    }

  def set_target_url(self, url):
    self.target_url = url

  def wait(self, a=0.1, b=0.2):
    random_wait = random.uniform(a, b)
    time.sleep(random_wait)

  def _log(self, message):
    if self.debug:
      ts = datetime.now().strftime("%H:%M:%S")
      print(f"[{ts}] [Crawler] {message}")

  def _safe_url(self):
    try:
      return self.driver.current_url
    except Exception:
      return "<unavailable>"

  def _strip_fragment(self, url):
    if not url:
      return url
    return url.split("#", 1)[0]

  def _driver_alive(self):
    try:
      _ = self.driver.window_handles
      return True
    except WebDriverException:
      return False

  def is_alive(self):
    return self._driver_alive()

  def current_url(self):
    return self._safe_url()

  def go(self, url):
    self.driver.get(url)
    WebDriverWait(self.driver, 10).until(
      lambda d: d.execute_script("return document.readyState") == "complete"
    )

  def on_list_page(self):
    return "/recipe/list.html" in self.current_url()

  def ensure_list_page(self, url=None):
    target = url or self.target_url
    if not self.on_list_page():
      self._log(f"recover list page -> {target}")
      self.go(target)
      self.dismiss_ads()

  def _describe_elem(self, elem):
    try:
      text = (elem.text or "").strip().replace("\n", " ")
      if len(text) > 40:
        text = text[:40] + "..."
      cls = elem.get_attribute("class") or ""
      return f"text='{text}' class='{cls}'"
    except Exception:
      return "<stale or unavailable>"

  def get_elem_xpath(self, xpath):
    return self.driver.find_element(By.XPATH, xpath)

  def get_elems_xpath(self, xpath):
    return self.driver.find_elements(By.XPATH, xpath)

  def get_elem_class(self,classname):
    return self.driver.find_element(By.CLASS_NAME, classname)


  def get_elem_id(self, id_):
    return self.driver.find_element(By.ID, id_)
  

  def back(self, wait_a=0.0, wait_b=0.0, timeout=10, fallback_url=None):
    before = self._safe_url()
    self._log(f"back() start url={before}")
    self.driver.back()

    moved = False
    if fallback_url:
      target = self._strip_fragment(fallback_url)
      try:
        WebDriverWait(self.driver, 2).until(
          lambda d: self._strip_fragment(d.current_url) == target
        )
        moved = True
      except TimeoutException:
        moved = False
    else:
      try:
        WebDriverWait(self.driver, 2).until(lambda d: d.current_url != before)
        moved = True
      except TimeoutException:
        moved = False

    if not moved:
      self._log("back() URL unchanged; trying history.go(-1)")
      try:
        self.driver.execute_script("window.history.go(-1);")
        if fallback_url:
          target = self._strip_fragment(fallback_url)
          WebDriverWait(self.driver, 2).until(
            lambda d: self._strip_fragment(d.current_url) == target
          )
          moved = True
        else:
          WebDriverWait(self.driver, 2).until(lambda d: d.current_url != before)
          moved = True
      except TimeoutException:
        moved = False

    if not moved:
      target = fallback_url or self.target_url
      self._log(f"back() still unchanged; navigating directly to {target}")
      self.driver.get(target)

    WebDriverWait(self.driver, timeout).until(
      lambda d: d.execute_script("return document.readyState") == "complete"
    )
    after = self._safe_url()
    self._log(f"back() done  url={after}")


    if wait_a != 0 and wait_b != 0:
      self.wait(wait_a, wait_b)

  def is_ad(self):
    try:
      self.driver.find_element(By.ID, "ad_position_box")
      return True
    except NoSuchElementException:
      pass

    return bool(self.driver.execute_script("""
      const isVisible = (el) => {
        if (!el) return false;
        const s = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && parseFloat(s.opacity || '1') > 0 &&
               r.width > 0 && r.height > 0;
      };

      const vw = window.innerWidth || document.documentElement.clientWidth;
      const vh = window.innerHeight || document.documentElement.clientHeight;
      const center = document.elementFromPoint(vw / 2, vh / 2);
      if (center && (center.tagName === 'IFRAME' || center.closest('iframe'))) return true;

      const candidates = Array.from(document.querySelectorAll('div,section,aside,iframe'));
      for (const el of candidates) {
        if (!isVisible(el)) continue;
        const r = el.getBoundingClientRect();
        const area = r.width * r.height;
        const s = getComputedStyle(el);
        const z = Number(s.zIndex) || 0;
        const fixedLike = s.position === 'fixed' || s.position === 'sticky';
        const large = area > (vw * vh * 0.2);
        const adLikeText = (el.innerText || '').includes('닫기') || (el.innerText || '').includes('열기');
        if (fixedLike && large && (z >= 100 || adLikeText || el.tagName === 'IFRAME')) return true;
      }
      return false;
    """))

  def _close_ad_overlays(self):
    if not self._driver_alive():
      return
    removed = self.driver.execute_script("""
      const isVisible = (el) => {
        if (!el) return false;
        const s = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' &&
               parseFloat(s.opacity || '1') > 0 && r.width > 0 && r.height > 0;
      };

      const vw = window.innerWidth || document.documentElement.clientWidth;
      const vh = window.innerHeight || document.documentElement.clientHeight;
      let clicked = 0;
      let removedFrames = 0;
      let removedOverlays = 0;

      // 1) Remove known ad iframes only.
      const frames = Array.from(document.querySelectorAll('iframe'));
      for (const f of frames) {
        const src = (f.getAttribute('src') || '').toLowerCase();
        const id = (f.getAttribute('id') || '').toLowerCase();
        const r = f.getBoundingClientRect();
        const area = Math.max(0, r.width) * Math.max(0, r.height);
        const fixedLike = getComputedStyle(f).position === 'fixed';
        const adLike = src.includes('googlesyndication') || id.startsWith('google_ads_iframe');
        if (adLike && (fixedLike || area > vw * vh * 0.2)) {
          f.remove();
          removedFrames += 1;
        }
      }

      // 2) Find center-blocking fixed modal only.
      const candidates = Array.from(document.querySelectorAll('div,section,aside'));
      const modal = candidates.find((el) => {
        if (!isVisible(el)) return false;
        const s = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        const area = r.width * r.height;
        const fixedLike = s.position === 'fixed' || s.position === 'sticky';
        const z = Number(s.zIndex) || 0;
        const blocksCenter = r.left <= vw / 2 && r.right >= vw / 2 && r.top <= vh / 2 && r.bottom >= vh / 2;
        return fixedLike && z >= 100 && area > vw * vh * 0.08 && blocksCenter;
      });

      if (modal) {
        // Click close inside modal only.
        const closeCandidates = modal.querySelectorAll(
          "[aria-label='닫기'],[aria-label*='close'],[title='닫기'],[title*='close']," +
          ".close,.btn_close,.popup_close,[class*='close'],[id*='close'],button"
        );
        for (const el of closeCandidates) {
          const t = (el.innerText || el.textContent || '').trim();
          const lbl = ((el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '')).toLowerCase();
          const closeLike = t === 'X' || t === 'x' || t === '✕' || t === '✖' || t === '×' ||
                            t.includes('닫기') || lbl.includes('close') || lbl.includes('닫기');
          if (closeLike && isVisible(el)) {
            el.click();
            clicked += 1;
            break;
          }
        }

        // If no close control found, remove the modal itself as last resort.
        if (clicked === 0) {
          modal.remove();
          removedOverlays += 1;
        }
      }

      document.body.style.overflow = 'auto';
      document.documentElement.style.overflow = 'auto';
      return { clicked, removedFrames, removedOverlays };
    """)
    self._log(
      f"dismiss ads: clicked={removed.get('clicked', 0)}, removed_iframe={removed.get('removedFrames', 0)}, "
      f"removed_overlay={removed.get('removedOverlays', 0)}"
    )

  def dismiss_ads(self):
    ad = self.is_ad()
    self._log(f"ad detected={ad}")
    if ad:
        self._close_ad_overlays()
    self.wait(0.1, 0.3)

  def click(self, elem, wait_a=0, wait_b=0):
    self.dismiss_ads()
    
    max_attempts = 4
    last_error = None
    self._log(f"click start target={self._describe_elem(elem)}")

    for attempt in range(1, max_attempts + 1):
      try:
        self.driver.execute_script(
          "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
          elem,
        )
        elem.click()
        self._log(f"click success attempt={attempt}")
        last_error = None
        break
      except (ElementClickInterceptedException, StaleElementReferenceException) as e:
        last_error = e
        self._log(f"click retry attempt={attempt} reason={type(e).__name__}")
        self._close_ad_overlays()
        try:
          self.driver.execute_script("arguments[0].click();", elem)
          self._log(f"js click success attempt={attempt}")
          last_error = None
          break
        except Exception as js_error:
          last_error = js_error
          self._log(f"js click failed attempt={attempt} reason={type(js_error).__name__}")
          self.wait(0.08, 0.2)

    if last_error is not None:
      self._log(f"click failed final reason={type(last_error).__name__}")
      return False

    if wait_a != 0 and wait_b != 0:
      self.wait(wait_a, wait_b)
    return True

  def type(self, elem, text, wait_a=0, wait_b=0):
    elem.send_keys(text)
    if wait_a != 0 and wait_b != 0:
      self.wait(wait_a, wait_b)

  def download(self, elem, wait_a=0, wait_b=0):
    if wait_a != 0 and wait_b != 0:
      self.wait(wait_a, wait_b)
    return elem.screenshot("./resultGraph.png")
