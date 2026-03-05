from KKSwx.KKSwx import KKSWx
import asyncio
wx = KKSWx()
hwnd = wx.find_all_windows_by_keyword("robot_test")[0]['hwnd']
async def test():
    queue = await wx.start(hwnd,"answerlabel")
    print(type(queue))
    while True:
        await asyncio.sleep(0.1)
        data = await queue.get()
        if data:
            print(data)

asyncio.run(test())
