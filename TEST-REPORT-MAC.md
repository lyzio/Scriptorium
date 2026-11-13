configfile: pytest.ini
testpaths: tests
collected 347 items                                                                                                           

tests/test_build.py ..............                                                                                      [  4%]
tests/test_file.py ........                                                                                             [  6%]
tests/test_fonts.py .....                                                                                               [  7%]
tests/test_m4.py ..............................                                                                         [ 16%]
tests/test_m5.py .............                                                                                          [ 20%]
tests/test_m5b.py .........                                                                                             [ 22%]
tests/test_m5c.py .......                                                                                               [ 24%]
tests/test_m5e.py .....                                                                                                 [ 26%]
tests/test_m6a.py ...........................                                                                           [ 34%]
tests/test_m6b.py ............                                                                                          [ 37%]
tests/test_m6c.py ...........................                                                                           [ 45%]
tests/test_m6c2.py ..................                                                                                   [ 50%]
tests/test_m6c3.py ..................                                                                                   [ 55%]
tests/test_m6c4.py ...........                                                                                          [ 58%]
tests/test_m6c5.py ............F.                                                                                       [ 62%]
tests/test_m6d.py .....                                                                                                 [ 64%]
tests/test_modules.py .............                                                                                     [ 68%]
tests/test_protect.py .......                                                                                           [ 70%]
tests/test_source.py ................                                                                                   [ 74%]
tests/test_ui_m2.py ..............                                                                                      [ 78%]
tests/test_ui_m2_fixes.py .....                                                                                         [ 80%]
tests/test_ui_m3.py .......                                                                                             [ 82%]
tests/test_ui_m4.py ..........                                                                                          [ 85%]
tests/test_ui_m5.py ...............                                                                                     [ 89%]
tests/test_ui_smoke.py ..........                                                                                       [ 92%]
tests/test_ui_strings.py ....                                                                                           [ 93%]
tests/test_world.py .......................                                                                             [100%]

========================================================== FAILURES ===========================================================
___________________________________________ test_T_UI_46_paragraphs_fill_the_width ____________________________________________

ui = <tests.test_ui_smoke.Driver object at 0x28716ae00>

    @pytest.mark.ui
    def test_T_UI_46_paragraphs_fill_the_width(ui):
        """T-UI-46 (issue #8): paragraphs and headings fill the editor column like
        the frames, in a narrow and a wide window, in full screen and with the
        preview hidden; nothing stops at about 100 characters."""
        load(ui, WIDTH_TEXT)
        top = "[...document.querySelectorAll('#visual > .blk-paragraph, #visual .blk-paragraph')][0]"
        inner = "document.querySelector('#visual .el-scene .blk-paragraph')"
    
        def measure(label):
            ui.wait(300)
            para = _width(ui, f"{top}.querySelector('.rich')")
            block = _width(ui, top)
            scene = _width(ui, "document.querySelector('#visual .el-scene')")
            inner_para = _width(ui, f"{inner}.querySelector('.rich')")
            inner_block = _width(ui, inner)
            heading = _width(ui, "document.querySelector('#visual .el-scene .heading-edit')")
            hundred = ui.js("(() => { const s = document.createElement('span'); s.textContent = '0'.repeat(100);"
                            f" const r = {top}.querySelector('.rich'); r.append(s); const w = s.getBoundingClientRect().width;"
                            " s.remove(); return w; })()")
            assert abs(para - block) <= 2, (label, para, block)
            assert abs(para - scene) <= 2, (label, para, scene)
            assert abs(inner_para - inner_block) <= 2, (label, inner_para, inner_block)
            assert abs(heading - inner_block) <= 2, (label, heading, inner_block)
            return para, hundred
    
        ui.window.resize(1000, 800)
        measure("narrow")
        ui.window.resize(2400, 1000)
        para, hundred = measure("wide")
>       assert para > hundred * 1.1, (para, hundred)
E       AssertionError: (968, 955.328125)
E       assert 968 > (955.328125 * 1.1)

tests/test_m6c5.py:791: AssertionError
=================================================== short test summary info ===================================================
FAILED tests/test_m6c5.py::test_T_UI_46_paragraphs_fill_the_width - AssertionError: (968, 955.328125)
========================================== 1 failed, 346 passed in 292.33s (0:04:52) 