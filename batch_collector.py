# encoding: utf-8
"""
小红书用户数据批量收集工具

功能包括：
1. 图片URL收集：获取用户所有笔记的图片URL并持久化保存
2. 评论收集：获取用户参与的评论会话并导出Excel

作者: AI Assistant
创建时间: 2024-11-17
"""

from xhs_utils.image_url_collector import UserImageUrlCollector, collect_user_images
from xhs_utils.comment_collector import UserCommentCollector, collect_user_comments
from loguru import logger
import time


class XHSUserDataCollector:
    """
    小红书用户数据收集器主入口
    """
    
    def __init__(self, output_dir="data"):
        """
        初始化数据收集器
        
        :param output_dir: 输出目录
        """
        self.output_dir = output_dir
        self.image_collector = UserImageUrlCollector(output_dir)
        self.comment_collector = UserCommentCollector(output_dir)
    
    def collect_all_data(self, user_url, cookies_str, proxies=None, 
                        collect_images=True, collect_comments=True, 
                        max_comment_notes=None):
        """
        一键收集用户的所有数据
        
        :param user_url: 用户主页URL
        :param cookies_str: Cookie字符串
        :param proxies: 代理设置
        :param collect_images: 是否收集图片URL
        :param collect_comments: 是否收集评论
        :param max_comment_notes: 评论收集时的最大笔记数量限制
        :return: 收集结果摘要
        """
        logger.info("🚀 开始一键收集用户数据...")
        
        user_id = self.image_collector.get_user_id_from_url(user_url)
        results = {
            "user_id": user_id,
            "user_url": user_url,
            "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "image_collection": None,
            "comment_collection": None
        }
        
        # 收集图片URL
        if collect_images:
            logger.info("📸 开始收集图片URL...")
            success, msg, data = self.image_collector.collect_user_image_urls(
                user_url, cookies_str, proxies, incremental=True
            )
            
            results["image_collection"] = {
                "success": success,
                "message": msg,
                "data": data
            }
            
            if success:
                logger.info("✅ 图片URL收集完成！")
                if data:
                    logger.info(f"   📊 总计: {data['total_notes']} 个笔记, {data['total_images']} 张图片")
            else:
                logger.error(f"❌ 图片URL收集失败: {msg}")
        
        # 收集评论
        if collect_comments:
            logger.info("💬 开始收集评论数据...")
            success, msg, data = self.comment_collector.collect_user_comments(
                user_url, cookies_str, proxies, max_comment_notes
            )
            
            results["comment_collection"] = {
                "success": success, 
                "message": msg,
                "data": data
            }
            
            if success:
                logger.info("✅ 评论收集完成！")
                if data:
                    logger.info(f"   📊 处理: {data['total_notes_processed']} 个笔记, " + 
                               f"找到: {data['total_comment_records']} 条相关评论")
            else:
                logger.error(f"❌ 评论收集失败: {msg}")
        
        results["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # 生成收集报告
        self.generate_collection_report(results)
        
        return results
    
    def generate_collection_report(self, results):
        """
        生成收集报告
        
        :param results: 收集结果
        """
        logger.info("\n" + "="*50)
        logger.info("📋 数据收集报告")
        logger.info("="*50)
        
        logger.info(f"🆔 用户ID: {results['user_id']}")
        logger.info(f"🔗 用户URL: {results['user_url']}")
        logger.info(f"⏰ 开始时间: {results['start_time']}")
        logger.info(f"⏰ 结束时间: {results['end_time']}")
        
        # 图片收集报告
        if results['image_collection']:
            img_result = results['image_collection']
            logger.info(f"\n📸 图片URL收集: {'✅ 成功' if img_result['success'] else '❌ 失败'}")
            if img_result['success'] and img_result['data']:
                data = img_result['data']
                logger.info(f"   📁 输出文件: {results['user_id']}_image_urls.json")
                logger.info(f"   📊 笔记总数: {data['total_notes']}")
                logger.info(f"   📊 图片总数: {data['total_images']}")
                logger.info(f"   📊 扫描时间: {data['scan_time']}")
            else:
                logger.info(f"   ❌ 失败原因: {img_result['message']}")
        
        # 评论收集报告
        if results['comment_collection']:
            comment_result = results['comment_collection']
            logger.info(f"\n💬 评论收集: {'✅ 成功' if comment_result['success'] else '❌ 失败'}")
            if comment_result['success'] and comment_result['data']:
                data = comment_result['data']
                logger.info(f"   📁 输出文件: {data['output_file']}")
                logger.info(f"   📊 处理笔记: {data['total_notes_processed']}")
                logger.info(f"   📊 有效笔记: {data['notes_with_comments']}")
                logger.info(f"   📊 评论会话: {data['total_comment_sessions']}")
                logger.info(f"   📊 评论记录: {data['total_comment_records']}")
            else:
                logger.info(f"   ❌ 失败原因: {comment_result['message']}")
        
        logger.info("="*50)


def quick_collect_images(user_url, cookies_str, output_dir="data", proxies=None):
    """
    快速收集图片URL
    
    :param user_url: 用户主页URL
    :param cookies_str: Cookie字符串
    :param output_dir: 输出目录
    :param proxies: 代理设置
    :return: (success, message, data)
    """
    return collect_user_images(user_url, cookies_str, output_dir, proxies)


def quick_collect_comments(user_url, cookies_str, output_dir="data", proxies=None, max_notes=None):
    """
    快速收集评论数据
    
    :param user_url: 用户主页URL  
    :param cookies_str: Cookie字符串
    :param output_dir: 输出目录
    :param proxies: 代理设置
    :param max_notes: 最大处理笔记数量
    :return: (success, message, data)
    """
    return collect_user_comments(user_url, cookies_str, output_dir, proxies, max_notes)


def quick_collect_all(user_url, cookies_str, output_dir="data", proxies=None, max_comment_notes=None):
    """
    一键收集所有数据
    
    :param user_url: 用户主页URL
    :param cookies_str: Cookie字符串  
    :param output_dir: 输出目录
    :param proxies: 代理设置
    :param max_comment_notes: 评论收集的最大笔记数量
    :return: 收集结果摘要
    """
    collector = XHSUserDataCollector(output_dir)
    return collector.collect_all_data(
        user_url, cookies_str, proxies,
        collect_images=True,
        collect_comments=True, 
        max_comment_notes=max_comment_notes
    )


if __name__ == "__main__":
    # 使用示例
    print("🔥 小红书用户数据批量收集工具")
    print("="*50)
    
    # 配置参数
    user_url = "https://www.xiaohongshu.com/user/profile/用户ID"
    cookies_str = "你的cookies字符串"
    output_dir = "data"
    proxies = None  # 如果需要代理：{"http": "http://proxy:port", "https": "https://proxy:port"}
    
    print("请配置以下参数后运行：")
    print(f"1. user_url = '{user_url}'")
    print(f"2. cookies_str = '{cookies_str}'")
    print(f"3. output_dir = '{output_dir}'")
    print(f"4. proxies = {proxies}")
    
    print("\n使用方式：")
    print("# 1. 只收集图片URL")
    print("success, msg, data = quick_collect_images(user_url, cookies_str)")
    
    print("\n# 2. 只收集评论（限制5个笔记用于测试）")
    print("success, msg, data = quick_collect_comments(user_url, cookies_str, max_notes=5)")
    
    print("\n# 3. 一键收集所有数据")
    print("results = quick_collect_all(user_url, cookies_str, max_comment_notes=10)")
    
    print("\n注意事项：")
    print("1. 确保cookies有效且格式正确")
    print("2. 建议先用较小的max_notes参数测试")
    print("3. 图片URL会保存为JSON文件，评论会保存为Excel文件")
    print("4. 支持增量更新，重复运行不会重复处理已有数据")