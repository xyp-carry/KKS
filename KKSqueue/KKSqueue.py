import asyncio
from typing import Optional, Any, Dict

class QueueManager:
    """
    异步队列管理器
    支持异步队列的创建、获取、销毁和状态监控。
    使用 asyncio.Lock 保证并发安全。
    """
    
    _instance = None
    _lock = asyncio.Lock() # 类级别的异步锁，用于单例创建保护

    def __new__(cls, *args, **kwargs):
        # 实现单例模式
        if not cls._instance:
            cls._instance = super(QueueManager, cls).__new__(cls)
            # 标记是否已初始化
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # 避免重复初始化
        if self._initialized:
            return
        
        self._queues: Dict[str, asyncio.Queue] = {}
        # 操作字典的异步锁
        self._manager_lock = asyncio.Lock()
        self._initialized = True

    async def create_queue(self, name: str, maxsize: int = 0) -> asyncio.Queue:
        """
        创建一个异步队列。如果队列已存在，则返回现有队列。
        
        :param name: 队列名称
        :param maxsize: 队列最大容量，0表示无限
        :return: asyncio.Queue 实例
        """
        async with self._manager_lock:
            if name not in self._queues:
                self._queues[name] = asyncio.Queue(maxsize=maxsize)
                print(f"[AsyncManager] 队列 '{name}' 创建成功 (maxsize={maxsize})")
            return self._queues[name]

    async def get_queue(self, name: str) -> Optional[asyncio.Queue]:
        """
        获取指定名称的队列。
        
        :param name: 队列名称
        :return: asyncio.Queue 实例，如果不存在返回 None
        """
        # 读操作通常加锁更安全，尽管在CPython中dict操作是原子的，
        # 但为了严谨性防止与写操作冲突，保持加锁
        async with self._manager_lock:
            return self._queues.get(name)

    async def destroy_queue(self, name: str) -> bool:
        """
        销毁指定名称的队列。
        会清空队列中的残留数据并删除引用。
        
        :param name: 队列名称
        :return: bool 是否销毁成功
        """
        async with self._manager_lock:
            if name in self._queues:
                q = self._queues[name]
                
                # 1. 清空队列残留数据
                # asyncio.Queue 没有 qsize() 保证精确，但 empty() 是可用的
                while not q.empty():
                    try:
                        # 使用 get_nowait 即时获取并丢弃
                        q.get_nowait()
                        # 标记任务完成（如果后续使用了 task_done）
                        q.task_done()
                    except asyncio.QueueEmpty:
                        break
                
                # 2. 从字典中移除引用
                del self._queues[name]
                print(f"[AsyncManager] 队列 '{name}' 已销毁")
                return True
            else:
                print(f"[AsyncManager] 队列 '{name}' 不存在，无需销毁")
                return False

    async def destroy_all(self):
        """
        销毁所有管理的队列
        """
        async with self._manager_lock:
            # 获取所有名称列表，逐一销毁
            # 注意：这里为了简化逻辑，我们在锁内直接操作，或者递归调用 destroy_queue
            # 由于 destroy_queue 本身也需要锁，我们需要小心死锁或重入问题
            # 最简单的方法是在这里直接操作内部数据
            names = list(self._queues.keys())
            for name in names:
                q = self._queues[name]
                while not q.empty():
                    try:
                        q.get_nowait()
                        q.task_done()
                    except asyncio.QueueEmpty:
                        break
                del self._queues[name]
                print(f"[AsyncManager] 队列 '{name}' 已销毁")
            
            print("[AsyncManager] 所有队列已销毁")

    async def get_status(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有队列的状态信息
        """
        async with self._manager_lock:
            status = {}
            for name, q in self._queues.items():
                status[name] = {
                    "size": q.qsize(),     # 大致大小
                    "maxsize": q.maxsize,
                    "empty": q.empty()
                }
            return status

# ==========================================
# 使用示例
# ==========================================

async def main():
    # 1. 获取管理器实例
    manager = QueueManager()

    # 2. 创建队列
    q1 = await manager.create_queue("task_queue", maxsize=10)
    print(f"队列实例: {q1}")

    # 3. 放入数据 (异步队列使用 await put，或者 put_nowait)
    await q1.put("Task A")
    q1.put_nowait("Task B")
    
    # 取出一条数据
    item = await q1.get()
    print(f"取出数据: {item}")
    
    print(f"当前状态: {await manager.get_status()}")

    # 4. 获取已存在的队列
    q_found = await manager.get_queue("task_queue")
    if q_found:
        print(f"从已获取队列中取出: {await q_found.get()}")

    # 5. 再次查看状态
    print(f"消费后状态: {await manager.get_status()}")

    # 6. 销毁队列
    await manager.destroy_queue("task_queue")
    
    # 7. 验证销毁
    print(f"销毁后状态: {await manager.get_status()}")

if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
