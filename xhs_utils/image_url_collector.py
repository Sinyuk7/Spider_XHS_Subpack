# encoding: utf-8
import json
import os
import time
from urllib.parse import urlparse
from loguru import logger
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.data_util import norm_str, check_and_create_path
from xhs_utils.rate_limiter import DEFAULT_RATE_LIMITER, with_rate_limit


class UserImageUrlCollector:
    """
    用户图片URL收集器
    负责获取指定用户所有笔记的图片URL并持久化保存
    """
    
    def __init__(self, output_dir="data"):
        """
        初始化收集器
        
        :param output_dir: 输出目录
        """
        self.output_dir = output_dir
        self.xhs_apis = XHS_Apis()
        
        # 确保输出目录存在
        check_and_create_path(self.output_dir)
    
    def get_user_id_from_url(self, user_url):
        """
        从用户URL中提取用户ID
        
        :param user_url: 用户主页URL
        :return: 用户ID
        """
        try:
            # 支持多种URL格式
            if '/user/profile/' in user_url:
                return user_url.split('/user/profile/')[-1].split('?')[0]
            elif 'user_id=' in user_url:
                return user_url.split('user_id=')[-1].split('&')[0]
            else:
                # 假设URL最后一部分是用户ID
                parsed = urlparse(user_url)
                return parsed.path.strip('/').split('/')[-1]
        except Exception as e:
            logger.error(f"解析用户URL失败: {user_url}, 错误: {e}")
            raise ValueError(f"无法解析用户URL: {user_url}")
    
    def load_existing_data(self, user_id):
        """
        加载已存在的数据文件
        
        :param user_id: 用户ID
        :return: 已存在的数据或空字典
        """
        file_path = os.path.join(self.output_dir, f"{user_id}_image_urls.json")
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"加载已存在数据：{len(data.get('notes', []))} 个笔记")
                    return data
            except Exception as e:
                logger.warning(f"加载已存在数据失败: {e}")
        
        # 返回默认结构
        return {
            "user_id": user_id,
            "nickname": "",
            "scan_time": "",
            "total_notes": 0,
            "total_images": 0,
            "notes": []
        }
    
    def save_data(self, data, user_id):
        """
        保存数据到文件
        
        :param data: 要保存的数据
        :param user_id: 用户ID
        """
        file_path = os.path.join(self.output_dir, f"{user_id}_image_urls.json")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"数据已保存到: {file_path}")
        except Exception as e:
            logger.error(f"保存数据失败: {e}")
            raise
    
    def extract_images_from_note(self, note_info):
        """
        从笔记信息中提取图片URL
        
        :param note_info: 笔记信息
        :return: 图片信息列表
        """
        images = []
        note_id = note_info.get('note_id', '')
        title = note_info.get('title', '无标题')
        
        # 清理标题，用于文件命名
        clean_title = norm_str(title)[:30]
        
        # 提取图片URL
        image_list = note_info.get('image_list', [])
        
        for index, img_url in enumerate(image_list):
            if img_url:  # 确保URL不为空
                filename = f"{clean_title}_{note_id}_{index}.jpg"
                images.append({
                    "index": index,
                    "url": img_url,
                    "filename": filename
                })
        
        return images
    
    @with_rate_limit(DEFAULT_RATE_LIMITER)
    def get_user_notes_with_rate_limit(self, user_url, cookies_str, proxies=None):
        """
        带频率控制的获取用户笔记方法
        """
        return self.xhs_apis.get_user_all_notes(user_url, cookies_str, proxies)
    
    @with_rate_limit(DEFAULT_RATE_LIMITER)
    def get_user_info_with_rate_limit(self, user_id, cookies_str, proxies=None):
        """
        带频率控制的获取用户信息方法
        """
        return self.xhs_apis.get_user_info(user_id, cookies_str, proxies)
    
    def collect_user_image_urls(self, user_url, cookies_str, proxies=None, incremental=True):
        """
        收集用户所有笔记的图片URL
        
        :param user_url: 用户主页URL
        :param cookies_str: Cookie字符串
        :param proxies: 代理设置
        :param incremental: 是否增量更新
        :return: (success, message, data)
        """
        try:
            # 提取用户ID
            user_id = self.get_user_id_from_url(user_url)
            logger.info(f"开始收集用户 {user_id} 的图片URL")
            
            # 加载已存在的数据
            if incremental:
                data = self.load_existing_data(user_id)
                existing_note_ids = {note['note_id'] for note in data['notes']}
                logger.info(f"增量模式：已存在 {len(existing_note_ids)} 个笔记")
            else:
                data = {
                    "user_id": user_id,
                    "nickname": "",
                    "scan_time": "",
                    "total_notes": 0,
                    "total_images": 0,
                    "notes": []
                }
                existing_note_ids = set()
            
            # 获取用户信息
            logger.info("获取用户基本信息...")
            success, msg, user_info = self.get_user_info_with_rate_limit(user_id, cookies_str, proxies)
            
            if success and user_info:
                from xhs_utils.data_util import handle_user_info
                user_data = handle_user_info(user_info['data'], user_id)
                data['nickname'] = user_data['nickname']
                logger.info(f"用户昵称: {data['nickname']}")
            
            # 获取用户所有笔记
            logger.info("获取用户所有笔记...")
            success, msg, notes_list = self.get_user_notes_with_rate_limit(user_url, cookies_str, proxies)
            
            if not success:
                logger.error(f"获取用户笔记失败: {msg}")
                return False, f"获取用户笔记失败: {msg}", None
            
            logger.info(f"获取到 {len(notes_list)} 个笔记")
            
            # 处理每个笔记
            new_notes_count = 0
            new_images_count = 0
            
            for i, note_info in enumerate(notes_list, 1):
                note_id = note_info.get('note_id', '')
                title = note_info.get('title', '无标题')
                
                # 检查是否已处理过
                if incremental and note_id in existing_note_ids:
                    logger.debug(f"跳过已存在笔记: {title} ({note_id})")
                    continue
                
                logger.info(f"处理笔记 {i}/{len(notes_list)}: {title}")
                
                # 提取图片URL
                images = self.extract_images_from_note(note_info)
                
                if images:
                    note_data = {
                        "note_id": note_id,
                        "title": title,
                        "note_type": note_info.get('note_type', '未知'),
                        "note_url": note_info.get('note_url', ''),
                        "upload_time": note_info.get('upload_time', ''),
                        "images": images
                    }
                    
                    data['notes'].append(note_data)
                    new_notes_count += 1
                    new_images_count += len(images)
                    
                    logger.info(f"  -> 发现 {len(images)} 张图片")
                
                # 每处理10个笔记保存一次
                if new_notes_count > 0 and new_notes_count % 10 == 0:
                    data['scan_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
                    data['total_notes'] = len(data['notes'])
                    data['total_images'] = sum(len(note['images']) for note in data['notes'])
                    self.save_data(data, user_id)
                    logger.info(f"中间保存完成，已处理 {new_notes_count} 个新笔记")
            
            # 最终保存
            data['scan_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
            data['total_notes'] = len(data['notes'])
            data['total_images'] = sum(len(note['images']) for note in data['notes'])
            self.save_data(data, user_id)
            
            logger.info(f"收集完成！新增 {new_notes_count} 个笔记，{new_images_count} 张图片")
            logger.info(f"总计 {data['total_notes']} 个笔记，{data['total_images']} 张图片")
            
            return True, "收集完成", data
            
        except Exception as e:
            logger.error(f"收集图片URL时发生错误: {e}")
            return False, str(e), None
    
    def get_summary(self, user_id):
        """
        获取收集结果摘要
        
        :param user_id: 用户ID
        :return: 摘要信息
        """
        try:
            data = self.load_existing_data(user_id)
            
            if not data['notes']:
                return "暂无数据"
            
            summary = f"""
📊 收集摘要
用户: {data['nickname']} ({data['user_id']})
扫描时间: {data['scan_time']}
笔记总数: {data['total_notes']}
图片总数: {data['total_images']}
数据文件: {user_id}_image_urls.json
            """
            
            return summary.strip()
            
        except Exception as e:
            return f"获取摘要失败: {e}"


# 使用示例函数
def collect_user_images(user_url, cookies_str, output_dir="data", proxies=None):
    """
    便捷函数：收集用户图片URL
    
    :param user_url: 用户主页URL
    :param cookies_str: Cookie字符串
    :param output_dir: 输出目录
    :param proxies: 代理设置
    :return: (success, message, data)
    """
    collector = UserImageUrlCollector(output_dir)
    return collector.collect_user_image_urls(user_url, cookies_str, proxies)


if __name__ == "__main__":
    # 测试代码
    user_url = "https://www.xiaohongshu.com/user/profile/用户ID"
    cookies_str = "你的cookies"
    
    success, msg, data = collect_user_images(user_url, cookies_str)
    
    if success:
        print("收集成功！")
        collector = UserImageUrlCollector()
        user_id = collector.get_user_id_from_url(user_url)
        print(collector.get_summary(user_id))
    else:
        print(f"收集失败: {msg}")