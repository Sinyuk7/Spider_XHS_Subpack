# encoding: utf-8
import json
import os
import time
from urllib.parse import urlparse
from loguru import logger
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.data_util import norm_str, check_and_create_path, save_to_xlsx, handle_comment_info
from xhs_utils.rate_limiter import DEFAULT_RATE_LIMITER, with_rate_limit


class UserCommentCollector:
    """
    用户评论收集器
    负责获取指定用户参与的评论会话并保存为Excel
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
    
    def filter_comments_with_target_user(self, all_comments, target_user_id):
        """
        过滤包含目标用户参与的评论会话
        
        :param all_comments: 所有评论列表
        :param target_user_id: 目标用户ID
        :return: 过滤后的评论列表
        """
        filtered_comments = []
        
        for comment in all_comments:
            # 检查一级评论作者是否是目标用户
            is_target_user_comment = comment.get('user_info', {}).get('user_id') == target_user_id
            
            # 检查二级评论中是否有目标用户
            has_target_user_reply = False
            sub_comments = comment.get('sub_comments', [])
            
            for sub_comment in sub_comments:
                if sub_comment.get('user_info', {}).get('user_id') == target_user_id:
                    has_target_user_reply = True
                    break
            
            # 如果目标用户参与了这个评论会话，保留整个会话
            if is_target_user_comment or has_target_user_reply:
                filtered_comments.append(comment)
                logger.debug(f"保留评论会话: {comment.get('content', '')[:30]}...")
        
        return filtered_comments
    
    def flatten_comments_for_excel(self, comments_data, target_user_id):
        """
        将嵌套的评论结构扁平化，用于Excel保存
        
        :param comments_data: 评论数据
        :param target_user_id: 目标用户ID
        :return: 扁平化的评论列表
        """
        flattened_comments = []
        
        for comment in comments_data:
            # 处理一级评论
            comment_info = handle_comment_info(comment)
            comment_info['comment_level'] = '一级评论'
            comment_info['is_target_user'] = comment_info['user_id'] == target_user_id
            flattened_comments.append(comment_info)
            
            # 处理二级评论
            for sub_comment in comment.get('sub_comments', []):
                sub_comment['note_id'] = comment.get('note_id', '')
                sub_comment['note_url'] = comment.get('note_url', '')
                
                sub_comment_info = handle_comment_info(sub_comment)
                sub_comment_info['comment_level'] = '二级回复'
                sub_comment_info['is_target_user'] = sub_comment_info['user_id'] == target_user_id
                sub_comment_info['parent_comment_id'] = comment.get('id', '')
                flattened_comments.append(sub_comment_info)
        
        return flattened_comments
    
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
    
    @with_rate_limit(DEFAULT_RATE_LIMITER)
    def get_note_comments_with_rate_limit(self, note_url, cookies_str, proxies=None):
        """
        带频率控制的获取笔记评论方法
        """
        return self.xhs_apis.get_note_all_comment(note_url, cookies_str, proxies)
    
    def collect_user_comments(self, user_url, cookies_str, proxies=None, max_notes=None):
        """
        收集用户参与的评论会话
        
        :param user_url: 用户主页URL
        :param cookies_str: Cookie字符串
        :param proxies: 代理设置
        :param max_notes: 最大处理笔记数量（None表示全部）
        :return: (success, message, data)
        """
        try:
            # 提取用户ID
            target_user_id = self.get_user_id_from_url(user_url)
            logger.info(f"开始收集用户 {target_user_id} 参与的评论")
            
            # 获取用户信息
            logger.info("获取用户基本信息...")
            success, msg, user_info = self.get_user_info_with_rate_limit(target_user_id, cookies_str, proxies)
            
            nickname = "未知用户"
            if success and user_info:
                from xhs_utils.data_util import handle_user_info
                user_data = handle_user_info(user_info['data'], target_user_id)
                nickname = user_data['nickname']
                logger.info(f"用户昵称: {nickname}")
            
            # 获取用户所有笔记
            logger.info("获取用户所有笔记...")
            success, msg, notes_list = self.get_user_notes_with_rate_limit(user_url, cookies_str, proxies)
            
            if not success:
                logger.error(f"获取用户笔记失败: {msg}")
                return False, f"获取用户笔记失败: {msg}", None
            
            # 限制处理的笔记数量
            if max_notes:
                notes_list = notes_list[:max_notes]
                logger.info(f"限制处理笔记数量为: {max_notes}")
            
            logger.info(f"获取到 {len(notes_list)} 个笔记")
            
            # 收集所有符合条件的评论
            all_filtered_comments = []
            processed_notes = 0
            notes_with_comments = 0
            
            for i, note_info in enumerate(notes_list, 1):
                note_url = note_info.get('note_url', '')
                title = note_info.get('title', '无标题')
                
                if not note_url:
                    logger.warning(f"笔记 {title} 缺少URL，跳过")
                    continue
                
                logger.info(f"处理笔记 {i}/{len(notes_list)}: {title[:30]}...")
                
                # 获取笔记评论
                success, msg, comments_data = self.get_note_comments_with_rate_limit(note_url, cookies_str, proxies)
                
                if not success:
                    logger.warning(f"获取笔记评论失败: {msg}")
                    continue
                
                if not comments_data:
                    logger.debug("该笔记没有评论")
                    processed_notes += 1
                    continue
                
                # 为每个评论添加笔记信息
                for comment in comments_data:
                    comment['note_id'] = note_info.get('note_id', '')
                    comment['note_url'] = note_url
                    comment['note_title'] = title
                
                # 过滤包含目标用户的评论会话
                filtered_comments = self.filter_comments_with_target_user(comments_data, target_user_id)
                
                if filtered_comments:
                    all_filtered_comments.extend(filtered_comments)
                    notes_with_comments += 1
                    logger.info(f"  -> 发现 {len(filtered_comments)} 个相关评论会话")
                else:
                    logger.debug("  -> 该笔记无目标用户参与的评论")
                
                processed_notes += 1
                
                # 每处理10个笔记输出一次进度
                if processed_notes % 10 == 0:
                    logger.info(f"已处理 {processed_notes}/{len(notes_list)} 个笔记，" +
                               f"找到 {len(all_filtered_comments)} 个相关评论会话")
            
            logger.info(f"处理完成！共处理 {processed_notes} 个笔记，" +
                       f"其中 {notes_with_comments} 个笔记有相关评论")
            logger.info(f"总共找到 {len(all_filtered_comments)} 个相关评论会话")
            
            if not all_filtered_comments:
                return True, "未找到用户参与的评论", []
            
            # 扁平化评论数据用于Excel保存
            flattened_comments = self.flatten_comments_for_excel(all_filtered_comments, target_user_id)
            
            # 保存为Excel
            output_file = os.path.join(self.output_dir, f"{target_user_id}_comments_filtered.xlsx")
            
            # 自定义Excel列标题
            self.save_comments_to_xlsx(flattened_comments, output_file)
            
            logger.info(f"评论数据已保存到: {output_file}")
            logger.info(f"共保存 {len(flattened_comments)} 条评论记录")
            
            return True, "收集完成", {
                "target_user_id": target_user_id,
                "nickname": nickname,
                "total_notes_processed": processed_notes,
                "notes_with_comments": notes_with_comments,
                "total_comment_sessions": len(all_filtered_comments),
                "total_comment_records": len(flattened_comments),
                "output_file": output_file
            }
            
        except Exception as e:
            logger.error(f"收集用户评论时发生错误: {e}")
            return False, str(e), None
    
    def save_comments_to_xlsx(self, comments_data, file_path):
        """
        保存评论数据到Excel，使用自定义列标题
        
        :param comments_data: 评论数据列表
        :param file_path: 输出文件路径
        """
        try:
            import openpyxl
            from xhs_utils.data_util import norm_text
            
            wb = openpyxl.Workbook()
            ws = wb.active
            
            # 自定义列标题
            headers = [
                '笔记ID', '笔记URL', '笔记标题', '评论ID', '用户ID', '用户主页URL', 
                '昵称', '头像URL', '评论内容', '评论标签', '点赞数量', '上传时间', 
                'IP归属地', '图片地址URL列表', '评论层级', '是否目标用户', '父评论ID'
            ]
            
            ws.append(headers)
            
            for comment in comments_data:
                row_data = [
                    comment.get('note_id', ''),
                    comment.get('note_url', ''),
                    comment.get('note_title', ''),
                    comment.get('comment_id', ''),
                    comment.get('user_id', ''),
                    comment.get('home_url', ''),
                    comment.get('nickname', ''),
                    comment.get('avatar', ''),
                    comment.get('content', ''),
                    comment.get('show_tags', ''),
                    comment.get('like_count', 0),
                    comment.get('upload_time', ''),
                    comment.get('ip_location', ''),
                    comment.get('pictures', []),
                    comment.get('comment_level', ''),
                    '是' if comment.get('is_target_user', False) else '否',
                    comment.get('parent_comment_id', '')
                ]
                
                # 清理数据中的特殊字符
                row_data = [norm_text(str(item)) for item in row_data]
                ws.append(row_data)
            
            wb.save(file_path)
            logger.info(f'评论数据已保存至 {file_path}')
            
        except Exception as e:
            logger.error(f"保存Excel文件失败: {e}")
            # 如果自定义保存失败，使用原有方法
            save_to_xlsx(comments_data, file_path, type='comment')
    
    def get_summary(self, target_user_id):
        """
        获取收集结果摘要
        
        :param target_user_id: 目标用户ID
        :return: 摘要信息
        """
        try:
            file_path = os.path.join(self.output_dir, f"{target_user_id}_comments_filtered.xlsx")
            
            if not os.path.exists(file_path):
                return "暂无数据文件"
            
            # 统计文件大小和修改时间
            file_size = os.path.getsize(file_path)
            file_mtime = time.ctime(os.path.getmtime(file_path))
            
            summary = f"""
📊 评论收集摘要
用户ID: {target_user_id}
数据文件: {target_user_id}_comments_filtered.xlsx
文件大小: {file_size / 1024:.1f} KB
更新时间: {file_mtime}
            """
            
            return summary.strip()
            
        except Exception as e:
            return f"获取摘要失败: {e}"


# 使用示例函数
def collect_user_comments(user_url, cookies_str, output_dir="data", proxies=None, max_notes=None):
    """
    便捷函数：收集用户参与的评论
    
    :param user_url: 用户主页URL
    :param cookies_str: Cookie字符串
    :param output_dir: 输出目录
    :param proxies: 代理设置
    :param max_notes: 最大处理笔记数量
    :return: (success, message, data)
    """
    collector = UserCommentCollector(output_dir)
    return collector.collect_user_comments(user_url, cookies_str, proxies, max_notes)


if __name__ == "__main__":
    # 测试代码
    user_url = "https://www.xiaohongshu.com/user/profile/用户ID"
    cookies_str = "你的cookies"
    
    # 限制处理5个笔记用于测试
    success, msg, data = collect_user_comments(user_url, cookies_str, max_notes=5)
    
    if success:
        print("收集成功！")
        if data:
            print(f"处理了 {data['total_notes_processed']} 个笔记")
            print(f"找到 {data['total_comment_records']} 条相关评论")
            print(f"保存到: {data['output_file']}")
        collector = UserCommentCollector()
        user_id = collector.get_user_id_from_url(user_url)
        print(collector.get_summary(user_id))
    else:
        print(f"收集失败: {msg}")