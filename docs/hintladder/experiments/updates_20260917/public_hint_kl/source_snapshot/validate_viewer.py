from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent


def main():
    data=json.loads((ROOT/'viewer_data.json').read_text())
    errors=[];checked=0
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport=dict(width=1440,height=1400))
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto((ROOT/'viewer.html').as_uri())
        page.locator('body[data-ready="true"]').wait_for()
        for index,pair in enumerate(data):
            page.locator('#sample').select_option(str(index))
            assert page.locator('body').get_attribute('data-sample')==str(pair['sample_id'])
            for arm in ['base','base_l1','base_l2','base_l3']:
                panel=page.locator(f'[data-arm="{arm}"]');ts=pair[arm]['turns']
                for pos in sorted({0,len(ts)//2,len(ts)-1}):
                    t=ts[pos];panel.locator('[data-role="turn"]').select_option(str(pos))
                    actual=panel.evaluate("el=>Object.fromEntries(['output','hint','observation','feedback'].map(k=>[k,el.querySelector('[data-role='+k+']').textContent]))")
                    assert actual==dict(output=t['output'],hint=t['hint'] or '无',observation=t['observation'],feedback=t['feedback'])
                    checked+=1
        sizes=[]
        for width in [1440,768,360]:
            page.set_viewport_size(dict(width=width,height=1400))
            size=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
            assert size['scroll']<=size['width'],size
            sizes.append(size)
        assert not errors,errors
        result=dict(tasks=len(data),trajectories=len(data)*4,checked_turns=checked,
            turn_selection='first, middle, final turn of every trajectory',raw_text_matches=True,
            sizes=sizes,page_errors=errors)
        (ROOT/'browser_validation.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
        browser.close()


if __name__=='__main__':main()
